export interface Option {
  id: string;
  text: string;
}

export interface Question {
  id: string;
  text: string;
  options: Option[];
  correctOptionId: string; // The ID of the correct option
}

export interface Test {
  id: string;
  userId: string; // ID del usuario propietario
  title: string;
  createdAt: number;
  questions: Question[];
}

export interface TestResult {
  id: string;
  userId: string; // ID del usuario que hizo el test
  testId: string;
  testTitle: string;
  date: number;
  score: number;
  totalQuestions: number;
  details: AnswerDetail[];
}

export interface AnswerDetail {
  questionId: string;
  questionText: string;
  selectedOptionId: string;
  correctOptionId: string;
  options: Option[];
  isCorrect: boolean;
}

export enum AppRoute {
  HOME = 'HOME',
  EDITOR = 'EDITOR',
  QUIZ = 'QUIZ',
  HISTORY = 'HISTORY',
  RESULT_DETAILS = 'RESULT_DETAILS'
}