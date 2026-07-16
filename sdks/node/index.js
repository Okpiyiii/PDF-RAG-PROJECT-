#!/usr/bin/env node

/**
 * PDF RAG Pipeline — Node.js SDK
 *
 * Communicates with the Python core engine via child process.
 * Provides an idiomatic async API for Node.js users.
 */

"use strict";

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

/**
 * @typedef {Object} PDFRAGConfig
 * @property {boolean} [enableOCR=true]
 * @property {string} [ocrLanguage="eng"]
 * @property {number} [ocrDPI=300]
 * @property {boolean} [enableTables=true]
 * @property {boolean} [enableLayoutDetection=true]
 * @property {boolean} [enableTagging=false]
 * @property {string|null} [outputDir=null]
 * @property {boolean} [includeBboxComments=true]
 * @property {string|null} [tesseractCmd=null]
 * @property {number|null} [maxPages=50]
 */

/**
 * @typedef {Object} BoundingBox
 * @property {number} page
 * @property {number} x0
 * @property {number} y0
 * @property {number} x1
 * @property {number} y1
 */

/**
 * @typedef {Object} DocumentElement
 * @property {string} type
 * @property {string} text
 * @property {BoundingBox} bbox
 * @property {Object} metadata
 */

/**
 * @typedef {Object} TableData
 * @property {string[][]} rows
 * @property {BoundingBox} bbox
 * @property {string[]} columnHeaders
 * @property {string[]} rowHeaders
 */

/**
 * @typedef {Object} PDFRAGResult
 * @property {string} filePath
 * @property {number} pageCount
 * @property {string} markdown
 * @property {string} json
 * @property {DocumentElement[]} elements
 * @property {TableData[]} tables
 */

const DEFAULT_CONFIG = Object.freeze({
  enableOCR: true,
  ocrLanguage: "eng",
  ocrDPI: 300,
  enableTables: true,
  enableLayoutDetection: true,
  enableTagging: false,
  outputDir: null,
  includeBboxComments: true,
  tesseractCmd: null,
  maxPages: 50,
});

/**
 * Normalize config, merging with defaults.
 * @param {Partial<PDFRAGConfig>} [config]
 * @returns {PDFRAGConfig}
 */
function normalizeConfig(config) {
  return { ...DEFAULT_CONFIG, ...config };
}

/**
 * Generate a temporary Python script that invokes the pipeline.
 * @param {string} filePath - Absolute path to the PDF
 * @param {PDFRAGConfig} config
 * @returns {string} Python script content
 */
function buildPythonScript(filePath, config) {
  const escaped = JSON.stringify(filePath);
  const c = JSON.stringify(config);

  return `
import json, sys, os
sys.path.insert(0, ${JSON.stringify(getEnginePath())})

from pdf_rag_pipeline import PDFPipeline
from pdf_rag_pipeline.models import ExtractionResult

pipeline = PDFPipeline(
    enable_ocr=${config.enableOCR ? "True" : "False"},
    ocr_language=${JSON.stringify(config.ocrLanguage)},
    ocr_dpi=${config.ocrDPI},
    enable_tables=${config.enableTables ? "True" : "False"},
    enable_layout_detection=${config.enableLayoutDetection ? "True" : "False"},
    enable_tagging=${config.enableTagging ? "True" : "False"},
    output_dir=${config.outputDir ? JSON.stringify(config.outputDir) : "None"},
    tesseract_cmd=${config.tesseractCmd ? JSON.stringify(config.tesseractCmd) : "None"},
    max_pages=${config.maxPages != null ? config.maxPages : "None"},
    md_kwargs={"include_bbox_comment": ${config.includeBboxComments ? "True" : "False"}},
)

result = pipeline.process(${escaped})
print(result.to_json())
`.trim();
}

/**
 * Resolve the path to the Python engine relative to this SDK.
 * @returns {string}
 */
function getEnginePath() {
  // Check common locations
  const candidates = [
    path.resolve(__dirname, "..", "..", "pdf_rag_pipeline"),
    path.resolve(__dirname, "..", "pdf_rag_pipeline"),
    path.resolve(process.cwd(), "pdf_rag_pipeline"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "pipeline.py"))) {
      return path.dirname(candidate);
    }
  }

  // Default: assume pdf_rag_pipeline is a package parent
  return path.resolve(__dirname, "..", "..");
}

/**
 * Spawn a Python process to run the pipeline.
 * @param {string} script - Python script content
 * @param {number} [timeoutMs=120000]
 * @returns {Promise<string>} stdout
 */
function runPythonScript(script, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    const pythonCmd = process.platform === "win32" ? "python" : "python3";

    const child = spawn(pythonCmd, ["-c", script], {
      cwd: getEnginePath(),
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    child.stdout.setEncoding("utf-8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });

    child.stderr.setEncoding("utf-8");
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`PDF processing timed out after ${timeoutMs}ms`));
    }, timeoutMs);

    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(`Python process exited with code ${code}: ${stderr}`));
        return;
      }
      resolve(stdout);
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new Error(`Failed to start Python: ${err.message}. Is Python 3.8+ installed?`));
    });
  });
}

/**
 * Parse the JSON output from the Python engine.
 * @param {string} jsonStr
 * @returns {PDFRAGResult}
 */
function parseResult(jsonStr) {
  const data = JSON.parse(jsonStr);

  return {
    filePath: data.file_path,
    pageCount: data.page_count,
    markdown: data.markdown,
    json: jsonStr,
    elements: data.elements,
    tables: data.tables,
  };
}

/**
 * PDF RAG Pipeline client for Node.js.
 *
 * @example
 * const { PDFRAGClient } = require("pdf-rag-sdk");
 *
 * const client = new PDFRAGClient();
 * const result = await client.process("./document.pdf");
 * console.log(result.markdown);
 *
 * // Save results
 * await client.saveMarkdown(result, "./output.md");
 * await client.saveJSON(result, "./output.json");
 */
class PDFRAGClient {
  /**
   * @param {Partial<PDFRAGConfig>} [config]
   */
  constructor(config) {
    this.config = normalizeConfig(config);
  }

  /**
   * Process a PDF file through the full pipeline.
   * @param {string} filePath - Path to the PDF (absolute or relative)
   * @returns {Promise<PDFRAGResult>}
   */
  async process(filePath) {
    const absPath = path.resolve(filePath);
    if (!fs.existsSync(absPath)) {
      throw new Error(`PDF file not found: ${absPath}`);
    }

    const script = buildPythonScript(absPath, this.config);
    const stdout = await runPythonScript(script);
    return parseResult(stdout);
  }

  /**
   * Process a PDF and return only Markdown.
   * @param {string} filePath
   * @returns {Promise<string>}
   */
  async processToMarkdown(filePath) {
    const result = await this.process(filePath);
    return result.markdown;
  }

  /**
   * Process a PDF and return parsed JSON object.
   * @param {string} filePath
   * @returns {Promise<Object>}
   */
  async processToJSON(filePath) {
    const result = await this.process(filePath);
    return JSON.parse(result.json);
  }

  /**
   * Process multiple PDFs concurrently.
   * @param {string[]} filePaths
   * @returns {Promise<PDFRAGResult[]>}
   */
  async processBatch(filePaths) {
    const results = await Promise.allSettled(
      filePaths.map((fp) => this.process(fp)),
    );

    return results.map((r, i) => {
      if (r.status === "fulfilled") {
        return r.value;
      }
      throw new Error(`Failed to process ${filePaths[i]}: ${r.reason.message}`);
    });
  }

  /**
   * Save a result's Markdown to a file.
   * @param {PDFRAGResult} result
   * @param {string} outputPath
   * @returns {Promise<string>} The output path
   */
  async saveMarkdown(result, outputPath) {
    const absPath = path.resolve(outputPath);
    await fs.promises.writeFile(absPath, result.markdown, "utf-8");
    return absPath;
  }

  /**
   * Save a result's JSON to a file.
   * @param {PDFRAGResult} result
   * @param {string} outputPath
   * @returns {Promise<string>} The output path
   */
  async saveJSON(result, outputPath) {
    const absPath = path.resolve(outputPath);
    await fs.promises.writeFile(absPath, result.json, "utf-8");
    return absPath;
  }

  /**
   * Generate an accessibility-compliant tagged PDF.
   * @param {string} inputPath
   * @param {string} outputPath
   * @returns {Promise<string>} The output path
   */
  async generateTaggedPDF(inputPath, outputPath) {
    const script = buildPythonScript(inputPath, {
      ...this.config,
      enableTagging: true,
    });
    await runPythonScript(script);
    return path.resolve(outputPath);
  }
}

/**
 * Convenience function for one-shot PDF processing.
 * @param {string} filePath
 * @param {Partial<PDFRAGConfig>} [config]
 * @returns {Promise<PDFRAGResult>}
 */
async function processPDF(filePath, config) {
  const client = new PDFRAGClient(config);
  return client.process(filePath);
}

module.exports = {
  PDFRAGClient,
  processPDF,
  DEFAULT_CONFIG,
};
