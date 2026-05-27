// ─────────────────────────────────────────────────────────────────────────────
// saveOCsToDrive + uploadToDocsumo
//
// Two ways an OC gets picked up:
//   AUTO:   Supplier emails caught by keyword filter (existing logic)
//   MANUAL: You apply the "OC-Upload" label to any email (e.g. internal forwards)
//           → script uploads it and swaps label to "OC-Saved"
//
// SETUP: In Apps Script editor → Project Settings → Script Properties, add:
//   DOCSUMO_API_KEY     → your Docsumo API key
//   DOCSUMO_DOC_TYPE_ID → others__vNgOt
// ─────────────────────────────────────────────────────────────────────────────

function saveOCsToDrive() {
  var FOLDER_NAME      = "OC Inbox";
  var LABEL_SAVED      = "OC-Saved";
  var LABEL_UPLOAD     = "OC-Upload";   // ← apply this manually to forwarded OCs

  var folders = DriveApp.getFoldersByName(FOLDER_NAME);
  var folder  = folders.hasNext() ? folders.next() : DriveApp.createFolder(FOLDER_NAME);
  var labelSaved  = GmailApp.getUserLabelByName(LABEL_SAVED)  || GmailApp.createLabel(LABEL_SAVED);
  var labelUpload = GmailApp.getUserLabelByName(LABEL_UPLOAD) || GmailApp.createLabel(LABEL_UPLOAD);

  var OC_KEYWORDS = [
    "Auftragsbestätigung", "Auftragsbestaetigung",
    "Order Confirmation",
    "Order Acknowledgement",
    "Order Acknowledgment",
    "Orderbevestiging",
    "Confirmation de commande",
    "Ordrebekræftelse",
    "Orderbekräftelse",
    "Tilausvahvistus",
    "AB Nr", "AB ",
    "Auftrag "
  ];

  var SKIP_PATTERNS = [
    /lieferschein/i,
    /delivery.?note/i,
    /rechnung/i,
    /invoice/i,
    /faktura/i,
    /proforma/i,
    /pro.?forma/i,
    /terms.*condition/i,
    /auftrag\s*-\s*[A-Z]/i,
    /\bDN-\d/i,
    /\bRE-\d/i
  ];

  function shouldSkip(filename) {
    for (var p = 0; p < SKIP_PATTERNS.length; p++) {
      if (SKIP_PATTERNS[p].test(filename)) return true;
    }
    return false;
  }

  function processAttachments(thread, messages, skipVanillaSteel) {
    var saved = 0;
    for (var j = 0; j < messages.length; j++) {
      var msg         = messages[j];
      var senderEmail = msg.getFrom().replace(/.*<|>.*/g, "").toLowerCase();
      if (skipVanillaSteel && senderEmail.indexOf("vanillasteel.com") !== -1) continue;
      var dateStr     = Utilities.formatDate(msg.getDate(), "Europe/Berlin", "yyyy-MM-dd");
      var domain      = senderEmail.split("@")[1] || "unknown";
      var attachments = msg.getAttachments();
      for (var k = 0; k < attachments.length; k++) {
        var att = attachments[k];
        if (att.getContentType() !== "application/pdf") continue;
        if (shouldSkip(att.getName())) continue;
        var filename = dateStr + "_" + domain + "_" + att.getName();
        folder.createFile(att).setName(filename);
        uploadToDocsumo(att, filename);
        saved++;
        Logger.log("Saved + uploaded: " + filename);
      }
    }
    return saved;
  }

  var total = 0;

  // ── AUTO: supplier emails caught by keyword filter ─────────────────────────
  var keywordQuery = OC_KEYWORDS.map(function(k) {
    return 'subject:"' + k + '"';
  }).join(" OR ");

  var autoThreads = GmailApp.search(
    "has:attachment filename:pdf (" + keywordQuery + ") -label:" + LABEL_SAVED,
    0, 20
  );
  for (var i = 0; i < autoThreads.length; i++) {
    var thread = autoThreads[i];
    total += processAttachments(thread, thread.getMessages(), true);
    thread.addLabel(labelSaved);
  }

  // ── MANUAL: anything you labelled "OC-Upload" (e.g. forwarded from colleague)
  var manualThreads = GmailApp.search("label:" + LABEL_UPLOAD, 0, 20);
  for (var m = 0; m < manualThreads.length; m++) {
    var thread = manualThreads[m];
    total += processAttachments(thread, thread.getMessages(), false);  // no sender filter
    thread.removeLabel(labelUpload);
    thread.addLabel(labelSaved);
  }

  Logger.log("Done. " + total + " OC PDF(s) saved.");
}


// ─────────────────────────────────────────────────────────────────────────────
// Upload a PDF to Docsumo for extraction
// ─────────────────────────────────────────────────────────────────────────────
function uploadToDocsumo(att, filename) {
  var props     = PropertiesService.getScriptProperties();
  var apiKey    = props.getProperty("DOCSUMO_API_KEY");
  var docTypeId = props.getProperty("DOCSUMO_DOC_TYPE_ID");

  if (!apiKey || !docTypeId) {
    Logger.log("DOCSUMO_API_KEY or DOCSUMO_DOC_TYPE_ID not set in Script Properties.");
    return;
  }

  // Use Apps Script's built-in multipart handling — pass payload as an object
  // and let UrlFetchApp build the multipart body correctly
  var pdfBlob = att.copyBlob()
                   .setName(filename)
                   .setContentType("application/pdf");

  var options = {
    method:  "post",
    headers: {
      "apikey":          apiKey,
      "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept":          "application/json",
      "Accept-Language": "en-US,en;q=0.9"
    },
    payload: {
      "type": docTypeId,   // Docsumo expects "type", not "doc_type"
      "file": pdfBlob
    },
    muteHttpExceptions: true
  };

  var response = UrlFetchApp.fetch(
    "https://app.docsumo.com/api/v1/eevee/apikey/upload/",
    options
  );

  var code = response.getResponseCode();
  if (code === 200 || code === 201) {
    Logger.log("Docsumo upload OK: " + filename);
  } else {
    Logger.log("Docsumo upload FAILED (" + code + "): " + response.getContentText() + " | " + filename);
  }
}
