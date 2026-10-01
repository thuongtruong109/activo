function parseHashed() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName("Signed");

  if (!sheet) {
    SpreadsheetApp.getUi().alert('Không tìm thấy tab "Signed".');
    return;
  }

  const range = sheet.getDataRange();
  const values = range.getValues();

  const results = [];

  for (let row = 0; row < values.length; row++) {
    for (let col = 0; col < values[row].length; col++) {
      const cellValue = values[row][col];

      if (typeof cellValue !== "string") {
        continue;
      }

      const text = cellValue.trim();

      if (!text) {
        continue;
      }

      const lines = text.split(/\r?\n/);

      for (const line of lines) {
        const trimmedLine = line.trim();

        if (!trimmedLine) {
          continue;
        }

        const commaIndex = trimmedLine.indexOf(",");

        if (commaIndex === -1) {
          continue;
        }

        const hwid = trimmedLine.substring(0, commaIndex).trim();

        const jwt = trimmedLine.substring(commaIndex + 1).trim();

        if (!hwid || !jwt) {
          continue;
        }

        if (jwt.split(".").length !== 3) {
          continue;
        }

        results.push([hwid, jwt]);
      }
    }
  }

  if (results.length === 0) {
    SpreadsheetApp.getUi().alert(
      'Không tìm thấy dữ liệu HWID + JWT trong tab "Signed".',
    );
    return;
  }

  sheet.clearContents();

  sheet.getRange(1, 1, 1, 2).setValues([["hwid", "token"]]);

  sheet.getRange(1, 1, 1, 2).setFontWeight("bold");

  sheet.getRange(2, 1, results.length, 2).setNumberFormat("@");

  sheet.getRange(2, 1, results.length, 2).setValues(results);

  sheet.autoResizeColumns(1, 2);

  SpreadsheetApp.getUi().alert(
    `Đã parse ${results.length} dòng HWID + JWT trong tab "Signed".`,
  );
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("HWID Parser")
    .addItem("Parse Signed", "parseHashed")
    .addToUi();
}
