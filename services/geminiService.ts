import { GoogleGenAI, Type, GenerateContentResponse } from "@google/genai";
import { Question } from "../types";
// @ts-ignore
import * as pdfjsLib from 'pdfjs-dist';

// Configurar el worker de PDF.js desde CDN para evitar problemas de bundler
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://esm.sh/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs`;

const generateId = () => Math.random().toString(36).substring(2, 9);

// Función auxiliar para extraer texto de un PDF en el navegador (ahorra tokens de IA)
const extractTextFromPDF = async (base64Data: string, onProgress?: (msg: string) => void): Promise<string> => {
  try {
    const pdfData = atob(base64Data);
    const loadingTask = pdfjsLib.getDocument({ data: pdfData });
    const pdf = await loadingTask.promise;
    
    let fullText = "";
    const numPages = pdf.numPages;

    for (let i = 1; i <= numPages; i++) {
      if (onProgress) onProgress(`Leyendo página ${i} de ${numPages}...`);
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items.map((item: any) => item.str).join(' ');
      fullText += `--- Page ${i} ---\n${pageText}\n`;
    }
    return fullText;
  } catch (error) {
    console.error("Error extrayendo texto PDF:", error);
    // Si falla la extracción local, devolvemos cadena vacía y se usará el método de imagen
    return "";
  }
};

export const parseFileToQuiz = async (base64Data: string, mimeType: string, onProgress?: (msg: string) => void): Promise<Question[]> => {
  const apiKey = process.env.API_KEY;

  if (!apiKey) {
    throw new Error("Falta la API Key.");
  }

  const ai = new GoogleGenAI({ apiKey: apiKey });
  let extractedText = "";

  // ESTRATEGIA DE AHORRO:
  // Si es un PDF, intentamos extraer el texto localmente.
  // Enviar texto consume MUCHO MENOS límite que enviar el PDF binario.
  if (mimeType.includes('pdf')) {
    if (onProgress) onProgress("Extrayendo texto del PDF...");
    extractedText = await extractTextFromPDF(base64Data, onProgress);
  }

  if (onProgress) onProgress("Analizando contenido con IA...");

  const systemInstruction = `
    You are an expert exam creator. Your goal is to extract multiple-choice questions from the provided content.
    Ignore headers, footers, page numbers, or section titles that interrupt the flow of questions.
    Extract ALL questions found.
    
    CRITICAL RULES:
    1. Output MUST be a clean JSON array.
    2. Remove numbering from the question text (e.g., "1. Question" -> "Question").
    3. Remove numbering from options (e.g., "a) Option" -> "Option").
    4. If a correct answer is indicated in the text (bolded, marked, or listed at the end), set 'c' to its index (0, 1, 2, 3). If not found, set 'c' to -1.
    5. Use strict JSON format.
  `;

  // Modelo: gemini-2.5-flash-latest es más estable y tiene límites más altos que la v3-preview
  const modelName = "gemini-2.5-flash-latest";

  try {
    let response: GenerateContentResponse;

    // Si pudimos extraer texto, enviamos solo texto (Rápido y barato)
    if (extractedText && extractedText.length > 50) {
       // Si el texto es muy largo, Gemini Flash tiene una ventana de contexto enorme (1M tokens),
       // así que podemos enviar libros enteros.
       response = await ai.models.generateContent({
        model: modelName,
        contents: {
          role: 'user',
          parts: [{ text: `Here is the text content of a test document:\n\n${extractedText}` }]
        },
        config: {
          systemInstruction: systemInstruction,
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.ARRAY,
            items: {
              type: Type.OBJECT,
              properties: {
                q: { type: Type.STRING }, // Question
                o: { type: Type.ARRAY, items: { type: Type.STRING } }, // Options
                c: { type: Type.INTEGER } // Correct Index
              },
              required: ["q", "o", "c"]
            }
          }
        }
      });
    } else {
      // Si es imagen o falló la extracción de texto, enviamos el binario (Más costoso)
      response = await ai.models.generateContent({
        model: modelName, // Usamos 2.5 Flash que soporta imágenes también
        contents: {
          role: 'user',
          parts: [
            {
              inlineData: {
                mimeType: mimeType,
                data: base64Data
              }
            },
            { text: "Extract all multiple choice questions from this document." }
          ]
        },
        config: {
          systemInstruction: systemInstruction,
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.ARRAY,
            items: {
              type: Type.OBJECT,
              properties: {
                q: { type: Type.STRING },
                o: { type: Type.ARRAY, items: { type: Type.STRING } },
                c: { type: Type.INTEGER }
              },
              required: ["q", "o", "c"]
            }
          }
        }
      });
    }

    if (onProgress) onProgress("Procesando estructura...");

    const responseText = response.text;
    if (!responseText) throw new Error("La IA no devolvió datos.");

    let jsonString = responseText.trim();
    if (jsonString.startsWith('```json')) jsonString = jsonString.replace(/^```json/, '').replace(/```$/, '').trim();
    else if (jsonString.startsWith('```')) jsonString = jsonString.replace(/^```/, '').replace(/```$/, '').trim();

    let rawData;
    try {
      rawData = JSON.parse(jsonString);
    } catch (e) {
      throw new Error("Error procesando la respuesta de la IA.");
    }

    if (!Array.isArray(rawData)) throw new Error("Formato inválido recibido.");

    return rawData.map((item: any) => {
      let cleanText = item.q || "Sin pregunta";
      // Limpieza agresiva de numeración
      cleanText = cleanText.replace(/^(\d+[\.\)\-]\s*)+/, "").trim();

      const options = (item.o || []).map((optText: string) => ({
        id: generateId(),
        text: optText.replace(/^([a-zA-Z\d][\.\)\-]\s*)+/, "").trim()
      }));

      let correctOptionId = "";
      if (typeof item.c === 'number' && item.c >= 0 && item.c < options.length) {
        correctOptionId = options[item.c].id;
      }

      return {
        id: generateId(),
        text: cleanText,
        options: options,
        correctOptionId: correctOptionId
      };
    });

  } catch (error: any) {
    console.error("Gemini Error:", error);
    if (error.message?.includes("429") || error.message?.includes("quota")) {
        throw new Error("⚠️ El sistema está saturado. Intenta subir menos páginas a la vez o espera 1 minuto.");
    }
    throw new Error("Error al analizar: " + error.message);
  }
};