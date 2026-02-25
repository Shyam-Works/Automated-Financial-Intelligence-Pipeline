import { spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";

interface CompanyRow {
  Company: string;
  "Period of Report": string;
  "Document Type": string;
  URL: string;
}

interface ExtractionResult {
  company: string;
  period: string;
  source_url: string;
  extracted_at: string;
  facts: any[];
  tables: any[];
  extraction_status: string;
  fact_count: number;
  error?: string;
}

interface PipelineStats {
  total_companies: number;
  successful_extractions: number;
  failed_extractions: number;
  total_facts_extracted: number;
  start_time: string;
  end_time: string;
  duration_seconds: number;
}

/**
 * Spawn Python script to extract and parse HTML
 */
export function spawnPy(payload: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const python = spawn("python", ["python/extract.py"], {
      stdio: ["pipe", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    python.stdout.on("data", (data) => {
      stdout += data.toString("utf-8");
    });

    python.stderr.on("data", (data) => {
      stderr += data.toString("utf-8");
    });

    python.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(stderr || `python exited with code ${code}`)
        );
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        reject(
          new Error(
            `Python did not return valid JSON.\nstdout:\n${stdout}\nstderr:\n${stderr}`
          )
        );
      }
    });

    python.stdin.write(JSON.stringify(payload));
    python.stdin.end();
  });
}

/**
 * Parse CSV file
 */
function parseCSV(filepath: string): CompanyRow[] {
  const content = fs.readFileSync(filepath, "utf-8");
  const lines = content.trim().split("\n");
  const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));

  const rows: CompanyRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    const row: any = {};
    headers.forEach((header, idx) => {
      row[header] = values[idx] || "";
    });
    rows.push(row as CompanyRow);
  }

  return rows;
}

/**
 * Parse a CSV line handling quoted values
 */
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];

    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current.trim());

  return result;
}

/**
 * Ensure output directory exists
 */
function ensureOutputDir(outDir: string): void {
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }
}

/**
 * Write JSONL file (one JSON object per line)
 */
function writeJSONL(filepath: string, data: any[]): void {
  const lines = data.map((item) => JSON.stringify(item)).join("\n");
  fs.writeFileSync(filepath, lines, "utf-8");
}

/**
 * Main pipeline execution
 */
async function runPipeline(inputFile: string, outDir: string): Promise<void> {
  console.log("=== SecLink Data Discovery Pipeline ===");
  console.log(`Input: ${inputFile}`);
  console.log(`Output: ${outDir}`);
  console.log("");

  const startTime = new Date();

  // Ensure output directory
  ensureOutputDir(outDir);

  // Parse input CSV
  console.log("Reading companies from CSV...");
  const companies = parseCSV(inputFile);
  console.log(`Found ${companies.length} companies to process\n`);

  // Track results
  const results: ExtractionResult[] = [];
  const errors: any[] = [];
  let successCount = 0;
  let failCount = 0;
  let totalFacts = 0;

  // Process each company
  for (let i = 0; i < companies.length; i++) {
    const company = companies[i];
    const num = i + 1;

    console.log(`[${num}/${companies.length}] Processing: ${company.Company}`);
    console.log(`  Period: ${company["Period of Report"]}`);
    console.log(`  URL: ${company.URL}`);

    try {
      const result = await spawnPy({
        url: company.URL,
        company: company.Company,
        period: company["Period of Report"],
      });

      if (result.extraction_status === "success") {
        successCount++;
        totalFacts += result.fact_count || 0;
        console.log(`  ✓ Success: Extracted ${result.fact_count} facts\n`);
      } else {
        console.log(`  ⚠ No facts found\n`);
      }

      results.push(result);
    } catch (error: any) {
      failCount++;
      console.log(`  ✗ Failed: ${error.message}\n`);

      const errorResult = {
        company: company.Company,
        period: company["Period of Report"],
        url: company.URL,
        error: error.message,
        extraction_status: "failed",
      };

      errors.push(errorResult);
      results.push(errorResult as any);
    }

    // Small delay between requests to be respectful
    if (i < companies.length - 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  const endTime = new Date();
  const duration = (endTime.getTime() - startTime.getTime()) / 1000;

  // Generate summary statistics
  const stats: PipelineStats = {
    total_companies: companies.length,
    successful_extractions: successCount,
    failed_extractions: failCount,
    total_facts_extracted: totalFacts,
    start_time: startTime.toISOString(),
    end_time: endTime.toISOString(),
    duration_seconds: duration,
  };

  // Write outputs
  console.log("=== Writing Outputs ===");

  // 1. All results (JSONL)
  const factsPath = path.join(outDir, "facts.jsonl");
  writeJSONL(factsPath, results);
  console.log(`✓ facts.jsonl (${results.length} records)`);

  // 2. Errors only (JSONL)
  if (errors.length > 0) {
    const errorsPath = path.join(outDir, "errors.jsonl");
    writeJSONL(errorsPath, errors);
    console.log(`✓ errors.jsonl (${errors.length} errors)`);
  }

  // 3. Summary (JSON)
  const summaryPath = path.join(outDir, "summary.json");
  fs.writeFileSync(summaryPath, JSON.stringify(stats, null, 2), "utf-8");
  console.log(`✓ summary.json`);

  // 4. Aggregated by company (JSON)
  const byCompany: { [key: string]: ExtractionResult[] } = {};
  results.forEach((result) => {
    if (!byCompany[result.company]) {
      byCompany[result.company] = [];
    }
    byCompany[result.company].push(result);
  });

  const companiesPath = path.join(outDir, "companies.json");
  fs.writeFileSync(companiesPath, JSON.stringify(byCompany, null, 2), "utf-8");
  console.log(`✓ companies.json`);

  // Print summary
  console.log("\n=== Pipeline Summary ===");
  console.log(`Total companies: ${stats.total_companies}`);
  console.log(`Successful: ${stats.successful_extractions}`);
  console.log(`Failed: ${stats.failed_extractions}`);
  console.log(`Total facts extracted: ${stats.total_facts_extracted}`);
  console.log(`Duration: ${stats.duration_seconds.toFixed(2)}s`);
  console.log(`\nOutputs written to: ${outDir}/`);
}

// CLI execution
const args = process.argv.slice(2);
const inputIndex = args.indexOf("--input");
const outIndex = args.indexOf("--out");

if (inputIndex === -1 || outIndex === -1) {
  console.error("Usage: npm run pipeline -- --input <csv-file> --out <output-dir>");
  process.exit(1);
}

const inputFile = args[inputIndex + 1];
const outDir = args[outIndex + 1];

runPipeline(inputFile, outDir).catch((error) => {
  console.error("Pipeline failed:", error);
  process.exit(1);
});