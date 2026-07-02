(() => {
    console.log("Starting Finacle TTUM Maker...");

    const STATIC_DEBIT_ACCOUNT = "12345678901234";
    const DEFAULT_NARRATION = "Share Fund Debit";
    const ALLOWED_EXTENSIONS = ["xlsx", "xls", "xlsb", "csv", "ods"];

    const fileInput = document.getElementById("excelFile");
    const recordsInput = document.getElementById("recordsPerFile");
    const processBtn = document.getElementById("processBtn");
    const statusBox = document.getElementById("statusBox");

    function setStatus(message, isError = false) {
        if (!statusBox) return;
        statusBox.textContent = message;
        statusBox.style.color = isError ? "#b42318" : "#222";
        statusBox.style.background = isError ? "#fef3f2" : "#f1f5f9";
        statusBox.style.borderColor = isError ? "#fecdca" : "#e5e7eb";
    }

    function getFileExtension(filename) {
        const parts = String(filename || "").split(".");
        return parts.length > 1 ? parts.pop().toLowerCase() : "";
    }

    function validateFile(file) {
        if (!file) {
            throw new Error("Please select an Excel file.");
        }

        const ext = getFileExtension(file.name);
        if (!ALLOWED_EXTENSIONS.includes(ext)) {
            throw new Error("Only Excel files are allowed: .xlsx, .xls, .xlsb, .csv, .ods");
        }
    }

    function validateRecordsPerFile(value) {
        const parsed = Number(value);

        if (!Number.isInteger(parsed) || parsed < 2) {
            throw new Error("Records per file must be an integer greater than or equal to 2.");
        }

        return parsed;
    }

    function formatAmount(amount) {
        const num = Number(amount);
        if (Number.isNaN(num)) {
            throw new Error(`Invalid amount found: ${amount}`);
        }
        return num.toFixed(2);
    }

    function truncateNarration(text) {
        const finalText = String(text || DEFAULT_NARRATION).trim() || DEFAULT_NARRATION;
        return finalText.substring(0, 30);
    }

    function buildTTUMLine(accountNumber, solId, drCr, amount, narration) {
        const amountStr = formatAmount(amount);

        let paddingCount = 17 - amountStr.length;
        if (paddingCount < 10) {
            paddingCount = 10;
        }

        const spaceStr = " ".repeat(paddingCount);
        const desc = truncateNarration(narration);

        return `${String(accountNumber).trim()} INR${String(solId).trim()}    ${drCr}${spaceStr}${amountStr}${desc}`;
    }

    function chunkArray(arr, size) {
        const out = [];
        for (let i = 0; i < arr.length; i += size) {
            out.push(arr.slice(i, i + size));
        }
        return out;
    }

    function downloadTextFile(filename, content) {
        const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function parseWorkbook(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = function (e) {
                try {
                    const data = e.target.result;
                    const workbook = XLSX.read(data, { type: "array" });
                    resolve(workbook);
                } catch (err) {
                    reject(err);
                }
            };

            reader.onerror = function () {
                reject(new Error("Unable to read the selected file."));
            };

            reader.readAsArrayBuffer(file);
        });
    }

    function extractRows(workbook) {
        const firstSheetName = workbook.SheetNames[0];
        if (!firstSheetName) {
            throw new Error("No sheet found in the uploaded workbook.");
        }

        const sheet = workbook.Sheets[firstSheetName];
        const rows = XLSX.utils.sheet_to_json(sheet, {
            defval: "",
            raw: false
        });

        if (!rows.length) {
            throw new Error("The uploaded Excel file is empty.");
        }

        const parsedRows = rows.map((row, index) => {
            const accountNumber = row["Account Number"];
            const solId = row["Sol ID"];
            const amount = row["Amount"];
            const narration = row["Narration"];

            if (!accountNumber) {
                throw new Error(`Missing Account Number in row ${index + 2}.`);
            }

            if (!solId) {
                throw new Error(`Missing Sol ID in row ${index + 2}.`);
            }

            if (amount === "" || amount === null || amount === undefined) {
                throw new Error(`Missing Amount in row ${index + 2}.`);
            }

            const numericAmount = Number(String(amount).toString().replace(/,/g, "").trim());

            if (Number.isNaN(numericAmount) || numericAmount <= 0) {
                throw new Error(`Invalid Amount in row ${index + 2}.`);
            }

            return {
                account_number: String(accountNumber).trim(),
                sol_id: String(solId).trim(),
                amount: numericAmount,
                narration: String(narration || "").trim() || DEFAULT_NARRATION
            };
        });

        return parsedRows;
    }

    function generateTTUMFiles(rows, recordsPerFile) {
        const creditPerFile = recordsPerFile - 1;

        if (creditPerFile < 1) {
            throw new Error("Records per file must allow at least 1 credit row and 1 debit row.");
        }

        const chunks = chunkArray(rows, creditPerFile);
        const outputs = [];

        chunks.forEach((chunk, index) => {
            const lines = [];
            let totalCredit = 0;

            chunk.forEach((row) => {
                totalCredit += row.amount;

                lines.push(
                    buildTTUMLine(
                        row.account_number,
                        row.sol_id,
                        "C",
                        row.amount,
                        row.narration
                    )
                );
            });

            const debitSolId = chunk[0].sol_id;

            lines.push(
                buildTTUMLine(
                    STATIC_DEBIT_ACCOUNT,
                    debitSolId,
                    "D",
                    totalCredit,
                    DEFAULT_NARRATION
                )
            );

            outputs.push({
                filename: `TTUM_${index + 1}.txt`,
                content: lines.join("\n"),
                credit_count: chunk.length,
                total_amount: totalCredit.toFixed(2),
                debit_sol_id: debitSolId
            });
        });

        return outputs;
    }

    if (!processBtn) {
        console.error("Process button not found.");
        return;
    }

    processBtn.addEventListener("click", async () => {
        try {
            setStatus("Processing...");
            const file = fileInput ? fileInput.files[0] : null;

            validateFile(file);

            const recordsPerFile = validateRecordsPerFile(recordsInput ? recordsInput.value : "");
            const workbook = await parseWorkbook(file);
            const rows = extractRows(workbook);
            const txtFiles = generateTTUMFiles(rows, recordsPerFile);

            txtFiles.forEach((fileObj) => {
                downloadTextFile(fileObj.filename, fileObj.content);
            });

            const summary = txtFiles.map((f, i) => {
                return `File ${i + 1}: ${f.credit_count} credit + 1 debit, debit amount ${f.total_amount}, Sol ID ${f.debit_sol_id}`;
            }).join("\n");

            setStatus(
                `Success.\nRows processed: ${rows.length}\nFiles generated: ${txtFiles.length}\n\n${summary}`
            );
        } catch (err) {
            console.error(err);
            setStatus(err.message || "Something went wrong.", true);
        }
    });
})();