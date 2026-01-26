import { GoogleGenAI, Type, GenerateContentResponse } from "@google/genai";
import { Question } from "../types";
// @ts-ignore
import * as pdfjsLib from 'pdfjs-dist';

// Configurar el worker de PDF.js desde CDN
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://esm.sh/pdfjs-dist@4.0.379/build/pdf.worker.min.mjs`;

const generateId = () => Math.random().toString(36).substring(2, 9);

// Usamos gemini-2.0-flash-exp que es muy rápido, soporta visión nativa y tiene buenos límites gratuitos.
const MODEL_NAME = "gemini-2.0-flash-exp"; 

// --- UTILIDADES ---

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// Compresión de imagen optimizada (Max 800px, Calidad 0.5)
const compressImage = (base64Str: string, mimeType: string): Promise<string> => {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.src = `data:${mimeType};base64,${base64Str}`;
    img.onload = () => {
      const canvas = document.createElement('canvas');
      let width = img.width;
      let height = img.height;
      
      const MAX_SIZE = 800; 
      if (width > height) {
        if (width > MAX_SIZE) {
          height *= MAX_SIZE / width;
          width = MAX_SIZE;
        }
      } else {
        if (height > MAX_SIZE) {
          width *= MAX_SIZE / height;
          height = MAX_SIZE;
        }
      }

      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
          resolve(base64Str);
          return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      // Calidad 0.5 para reducir drásticamente el tamaño en bytes y tokens
      const newDataUrl = canvas.toDataURL('image/jpeg', 0.5);
      resolve(newDataUrl.split(',')[1]);
    };
    img.onerror = (e) => {
      console.warn("Error comprimiendo imagen", e);
      resolve(base64Str);
    };
  });
};

const extractTextFromPDF = async (base64Data: string, onProgress?: (msg: string, percent: number) => void): Promise<string> => {
  try {
    const pdfData = atob(base64Data);
    const loadingTask = pdfjsLib.getDocument({ data: pdfData });
    const pdf = await loadingTask.promise;
    
    let fullText = "";
    const numPages = pdf.numPages;
    const maxPages = Math.min(numPages, 5); 

    for (let i = 1; i <= maxPages; i++) {
      const percent = Math.round((i / maxPages) * 60);
      if (onProgress) onProgress(`Leyendo página ${i} de ${numPages}...`, percent);
      
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items.map((item: any) => item.str).join(' ');
      fullText += `--- Page ${i} ---\n${pageText}\n`;
    }
    return fullText;
  } catch (error) {
    console.error("Error PDF:", error);
    return "";
  }
};

// --- FUNCIÓN PRINCIPAL ---

export const parseFileToQuiz = async (
    base64Data: string, 
    mimeType: string, 
    onProgress?: (msg: string, percent: number) => void
): Promise<Question[]> => {
    
  const apiKey = process.env.API_KEY;
  if (!apiKey) throw new Error("Falta la API Key. Verifica tu archivo .env");

  const ai = new GoogleGenAI({ apiKey: apiKey });
  let contentToSend: any = null;

  // Preparación del contenido
  if (mimeType.includes('pdf')) {
    if (onProgress) onProgress("Procesando PDF...", 10);
    const extractedText = await extractTextFromPDF(base64Data, onProgress);
    if (extractedText && extractedText.length > 50) {
       contentToSend = { text: `Extract questions from this text:\n\n${extractedText}` };
    }
  } else if (mimeType.startsWith('image/')) {
    if (onProgress) onProgress("Optimizando imagen...", 20);
    const compressedBase64 = await compressImage(base64Data, mimeType);
    contentToSend = {
      inlineData: {
        mimeType: 'image/jpeg',
        data: compressedBase64
      }
    };
  }

  if (!contentToSend) {
    contentToSend = { inlineData: { mimeType: mimeType, data: base64Data } };
  }

  if (onProgress) onProgress("Conectando con la IA...", 60);

  // Instrucciones más concisas para ahorrar tokens de entrada
  const systemInstruction = `Extract multiple-choice questions. Rules: Output JSON array. Keys: "q"(text), "o"(options array), "c"(correct index 0-3). Remove numbering.`;

  const MAX_RETRIES = 3; // Reducimos intentos pero aumentamos la espera inteligente
  let lastError: any;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      if (onProgress && attempt > 1) onProgress(`Reintentando (${attempt}/${MAX_RETRIES})...`, 70);
      
      const response: GenerateContentResponse = await ai.models.generateContent({
        model: MODEL_NAME,
        contents: {
          role: 'user',
          parts: [
            contentToSend,
            ...(contentToSend.text ? [] : [{ text: "Extract questions. Return JSON." }])
          ]
        },
        config: {
          systemInstruction: systemInstruction,
          responseMimeType: "application/json",
          temperature: 0.1,
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

      if (onProgress) onProgress("Procesando...", 90);

      const responseText = response.text;
      if (!responseText) throw new Error("Respuesta vacía");

      let jsonString = responseText.trim();
      if (jsonString.startsWith('```json')) jsonString = jsonString.replace(/^```json/, '').replace(/```$/, '').trim();
      else if (jsonString.startsWith('```')) jsonString = jsonString.replace(/^```/, '').replace(/```$/, '').trim();

      const rawData = JSON.parse(jsonString);
      if (!Array.isArray(rawData)) throw new Error("Formato inválido");

      if (onProgress) onProgress("Listo!", 100);

      return rawData.map((item: any) => {
        let cleanText = item.q || "Sin pregunta";
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
      lastError = error;
      const msg = error.message?.toLowerCase() || "";
      
      console.warn(`Intento ${attempt} fallido:`, msg);

      // Si es un error de "No encontrado" (404), el modelo no existe, no tiene sentido reintentar.
      if (msg.includes("404") || msg.includes("not found")) {
         throw new Error("El modelo de IA seleccionado no está disponible. Contacta con el soporte.");
      }

      // Si es error de cuota (429), esperamos
      if (msg.includes("429") || msg.includes("503") || msg.includes("quota") || msg.includes("exhausted")) {
         if (attempt < MAX_RETRIES) {
            const delay = 4000 * attempt; // Espera progresiva: 4s, 8s...
            if (onProgress) onProgress(`IA saturada. Esperando ${delay/1000}s...`, 65);
            await wait(delay);
            continue;
         }
      } else {
        break; // Otros errores no se reintentan
      }
    }
  }

  if (lastError?.message?.includes("429") || lastError?.message?.includes("quota")) {
      throw new Error("⚠️ El sistema está saturado. Tu cuenta gratuita de IA ha alcanzado el límite de velocidad. Espera 1-2 minutos.");
  }
  
  throw new Error("No se pudo analizar. Verifica tu conexión o intenta con otra imagen.");
};