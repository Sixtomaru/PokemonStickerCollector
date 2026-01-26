import { Test, TestResult } from '../types';
import { db } from './firebaseConfig';
import { 
  collection, 
  doc, 
  setDoc, 
  getDoc, 
  getDocs, 
  deleteDoc, 
  query, 
  where
} from 'firebase/firestore';

export const storageService = {
  // --- Tests ---
  
  // Guardar un test (Nuevo o Editar)
  saveTest: async (test: Test): Promise<void> => {
    try {
      await setDoc(doc(db, "tests", test.id), test);
    } catch (e) {
      console.error("Error guardando test: ", e);
      throw e;
    }
  },

  // Obtener todos los tests DE UN USUARIO ESPECÍFICO
  getTests: async (userId: string): Promise<Test[]> => {
    try {
      if (!userId) return [];
      // Filtramos por userId sin orderBy para evitar errores de índice "Missing Index" en Firestore
      const q = query(
        collection(db, "tests"), 
        where("userId", "==", userId)
      );
      const querySnapshot = await getDocs(q);
      const tests: Test[] = [];
      querySnapshot.forEach((doc) => {
        tests.push(doc.data() as Test);
      });
      // Ordenamos en el cliente (JavaScript)
      return tests.sort((a, b) => b.createdAt - a.createdAt);
    } catch (e) {
      console.error("Error obteniendo tests: ", e);
      return [];
    }
  },

  // Obtener un test por ID (Público para compartir, si las reglas de Firebase lo permiten)
  getTestById: async (id: string): Promise<Test | undefined> => {
    try {
      const docRef = doc(db, "tests", id);
      const docSnap = await getDoc(docRef);
      if (docSnap.exists()) {
        return docSnap.data() as Test;
      } else {
        return undefined;
      }
    } catch (e) {
      console.error("Error obteniendo test: ", e);
      return undefined;
    }
  },

  // Copiar un test de otro usuario al usuario actual
  copyTest: async (originalTestId: string, newUserId: string): Promise<string> => {
      const original = await storageService.getTestById(originalTestId);
      if (!original) throw new Error("Test original no encontrado");

      const newId = Math.random().toString(36).substring(2, 9);
      const newTest: Test = {
          ...original,
          id: newId,
          userId: newUserId,
          title: `${original.title} (Copia)`,
          createdAt: Date.now()
      };
      
      await setDoc(doc(db, "tests", newId), newTest);
      return newId;
  },

  // Borrar un test
  deleteTest: async (id: string): Promise<void> => {
    try {
      await deleteDoc(doc(db, "tests", id));
    } catch (e) {
      console.error("Error borrando test: ", e);
      throw e;
    }
  },

  // --- Resultados / Historial ---

  // Guardar resultado
  saveResult: async (result: TestResult): Promise<void> => {
    try {
      await setDoc(doc(db, "results", result.id), result);
    } catch (e) {
      console.error("Error guardando resultado: ", e);
      throw e;
    }
  },

  // Obtener historial DE UN USUARIO
  getResults: async (userId: string): Promise<TestResult[]> => {
    try {
      if (!userId) return [];
      // Filtramos por userId sin orderBy para evitar errores de índice
      const q = query(
        collection(db, "results"), 
        where("userId", "==", userId)
      );
      const querySnapshot = await getDocs(q);
      const results: TestResult[] = [];
      querySnapshot.forEach((doc) => {
        results.push(doc.data() as TestResult);
      });
      // Ordenamos en el cliente
      return results.sort((a, b) => b.date - a.date);
    } catch (e) {
      console.error("Error obteniendo resultados: ", e);
      return [];
    }
  },

  // Obtener resultado por ID
  getResultById: async (id: string): Promise<TestResult | undefined> => {
    try {
      const docRef = doc(db, "results", id);
      const docSnap = await getDoc(docRef);
      if (docSnap.exists()) {
        return docSnap.data() as TestResult;
      } else {
        return undefined;
      }
    } catch (e) {
      console.error("Error obteniendo resultado: ", e);
      return undefined;
    }
  },

  // Borrar resultado individual
  deleteResult: async (id: string): Promise<void> => {
    try {
      await deleteDoc(doc(db, "results", id));
    } catch (e) {
      console.error("Error borrando resultado: ", e);
      throw e;
    }
  },

  // Borrar TODOS los resultados de un usuario
  deleteAllResults: async (userId: string): Promise<void> => {
    try {
      const q = query(collection(db, "results"), where("userId", "==", userId));
      const querySnapshot = await getDocs(q);
      const promises = querySnapshot.docs.map(d => deleteDoc(d.ref));
      await Promise.all(promises);
    } catch (e) {
      console.error("Error borrando todo el historial: ", e);
      throw e;
    }
  }
};