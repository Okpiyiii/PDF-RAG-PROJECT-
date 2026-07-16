/**
 * TypeScript type declarations for pdf-rag-sdk
 */

declare module "pdf-rag-sdk" {
  export interface PDFRAGConfig {
    enableOCR?: boolean;
    ocrLanguage?: string;
    ocrDPI?: number;
    enableTables?: boolean;
    enableLayoutDetection?: boolean;
    enableTagging?: boolean;
    outputDir?: string | null;
    includeBboxComments?: boolean;
    tesseractCmd?: string | null;
    maxPages?: number | null;
  }

  export interface BoundingBox {
    page: number;
    x0: number;
    y0: number;
    x1: number;
    y1: number;
  }

  export interface DocumentElement {
    type: string;
    text: string;
    bbox: BoundingBox;
    metadata: Record<string, unknown>;
  }

  export interface TableData {
    rows: string[][];
    bbox: BoundingBox;
    columnHeaders: string[];
    rowHeaders: string[];
  }

  export interface PDFRAGResult {
    filePath: string;
    pageCount: number;
    markdown: string;
    json: string;
    elements: DocumentElement[];
    tables: TableData[];
  }

  export class PDFRAGClient {
    constructor(config?: Partial<PDFRAGConfig>);
    process(filePath: string): Promise<PDFRAGResult>;
    processToMarkdown(filePath: string): Promise<string>;
    processToJSON(filePath: string): Promise<Record<string, unknown>>;
    processBatch(filePaths: string[]): Promise<PDFRAGResult[]>;
    saveMarkdown(result: PDFRAGResult, outputPath: string): Promise<string>;
    saveJSON(result: PDFRAGResult, outputPath: string): Promise<string>;
    generateTaggedPDF(inputPath: string, outputPath: string): Promise<string>;
  }

  export function processPDF(
    filePath: string,
    config?: Partial<PDFRAGConfig>,
  ): Promise<PDFRAGResult>;

  export const DEFAULT_CONFIG: PDFRAGConfig;
}
