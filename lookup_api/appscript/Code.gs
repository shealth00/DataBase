// Sally Health — Patient Lookup Apps Script
// Paste into Extensions -> Apps Script (or script.google.com).
//
// Script Properties (Extensions -> Apps Script -> Project Settings -> Script Properties):
//   SALLY_API_KEY   = <key from setup_from_mac.sh>
//   SALLY_BASE_URL  = http://129.80.132.81  (or https://api.sallyhealth.org after certbot)

const PROPS = PropertiesService.getScriptProperties();
const BASE  = (PROPS.getProperty("SALLY_BASE_URL") || "http://129.80.132.81").replace(/\/$/, "");
const KEY   = PROPS.getProperty("SALLY_API_KEY") || "";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Sally Health")
    .addItem("Patient Lookup Sidebar", "showLookupSidebar")
    .addItem("Import This Sheet", "importActiveSheet")
    .addItem("Report: Status", "reportStatus")
    .addItem("Report: Payer", "reportPayer")
    .addItem("API Health Check", "healthCheck")
    .addToUi();
}

function showLookupSidebar() {
  const html = HtmlService.createHtmlOutput(SIDEBAR_HTML)
    .setTitle("Patient Lookup")
    .setWidth(380);
  SpreadsheetApp.getUi().showSidebar(html);
}

// Called from sidebar JS via google.script.run
function lookupPatients(params) {
  const qs = Object.entries(params)
    .filter(([, v]) => v)
    .map(([k, v]) => encodeURIComponent(k) + "=" + encodeURIComponent(v))
    .join("&");
  const url = BASE + "/api/sh/patient-lookup" + (qs ? "?" + qs : "");
  const resp = UrlFetchApp.fetch(url, {
    headers: { "X-API-Key": KEY },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error("API " + resp.getResponseCode() + ": " + resp.getContentText().slice(0, 200));
  }
  return JSON.parse(resp.getContentText());
}

function importActiveSheet() {
  const ss    = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();
  const data  = sheet.getDataRange().getValues();
  if (data.length < 2) {
    SpreadsheetApp.getUi().alert("Sheet has no data rows.");
    return;
  }
  const headers = data[0].map(h => String(h).trim().toLowerCase().replace(/\s+/g, "_"));
  const rows = [];
  for (let i = 1; i < data.length; i++) {
    const row = {};
    headers.forEach((h, j) => { if (data[i][j] !== "") row[h] = data[i][j]; });
    rows.push(row);
  }
  const payload = {
    source: ss.getName() + " / " + sheet.getName() + " (" + new Date().toLocaleDateString() + ")",
    loaded_by: Session.getEffectiveUser().getEmail(),
    rows: rows
  };
  const resp = UrlFetchApp.fetch(BASE + "/api/sh/import", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    headers: { "X-API-Key": KEY },
    muteHttpExceptions: true
  });
  const body = JSON.parse(resp.getContentText());
  if (resp.getResponseCode() !== 200 || !body.ok) {
    SpreadsheetApp.getUi().alert("Import failed: " + JSON.stringify(body));
    return;
  }
  SpreadsheetApp.getUi().alert(
    "Import complete!\nPatients: " + body.patients +
    "\nEncounters: " + body.encounters +
    "\nTests: " + body.tests +
    "\nBatch ID: " + body.batch_id
  );
}

function reportStatus() { _writeReport("status"); }
function reportPayer()  { _writeReport("payer"); }

function _writeReport(type) {
  const resp = UrlFetchApp.fetch(BASE + "/api/sh/report?type=" + type, {
    headers: { "X-API-Key": KEY },
    muteHttpExceptions: true
  });
  const body = JSON.parse(resp.getContentText());
  if (!body.rows || body.rows.length === 0) {
    SpreadsheetApp.getUi().alert("No data for report type: " + type);
    return;
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName("Report_" + type);
  if (!sheet) sheet = ss.insertSheet("Report_" + type);
  sheet.clearContents();
  const headers = Object.keys(body.rows[0]);
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  const vals = body.rows.map(r => headers.map(h => r[h] != null ? r[h] : ""));
  sheet.getRange(2, 1, vals.length, headers.length).setValues(vals);
  ss.setActiveSheet(sheet);
  SpreadsheetApp.getUi().alert("Report '" + type + "' written to sheet Report_" + type + ".");
}

function healthCheck() {
  try {
    const resp = UrlFetchApp.fetch(BASE + "/api/sh/health", { muteHttpExceptions: true });
    const body = JSON.parse(resp.getContentText());
    SpreadsheetApp.getUi().alert(
      body.ok
        ? "API OK — " + body.patients + " patients in database."
        : "API error: " + body.error
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert(
      "Cannot reach API: " + e.message +
      "\n\nCheck:\n1. OCI Security List port 80 open\n2. sudo ufw allow 80/tcp on vm-01\n3. systemctl status sally-lookup on vm-01"
    );
  }
}

const SIDEBAR_HTML = `<!DOCTYPE html>
<html>
<head>
<style>
  body{font-family:Arial,sans-serif;font-size:13px;padding:10px;margin:0}
  label{font-weight:bold;color:#333;display:block;margin-top:8px}
  input{width:100%;box-sizing:border-box;padding:5px;border:1px solid #ccc;border-radius:3px;margin-top:2px}
  button{background:#1a73e8;color:#fff;border:none;padding:8px 0;border-radius:4px;cursor:pointer;width:100%;margin-top:10px;font-size:13px}
  button:hover{background:#1558b0}
  .patient{border:1px solid #e0e0e0;border-radius:4px;padding:8px;margin:6px 0;font-size:12px}
  .name{font-weight:bold;font-size:13px;margin-bottom:2px}
  .err{color:red}
  #results{margin-top:12px}
</style>
</head>
<body>
<b>Patient Lookup</b>
<label>Free search (name or member ID)
<input id="q" placeholder="Smith or MBR12345"></label>
<label>Last name<input id="last" placeholder="Smith"></label>
<label>First name<input id="first" placeholder="Jane"></label>
<label>Date of birth<input id="dob" placeholder="YYYY-MM-DD"></label>
<button onclick="search()">Search</button>
<div id="results"></div>
<script>
function search(){
  var p={q:v('q'),last:v('last'),first:v('first'),dob:v('dob')};
  document.getElementById('results').innerHTML='Searching…';
  google.script.run.withSuccessHandler(show).withFailureHandler(err).lookupPatients(p);
}
function v(id){return document.getElementById(id).value.trim();}
function show(d){
  var el=document.getElementById('results');
  if(!d.results||!d.results.length){el.innerHTML='<i>No patients found.</i>';return;}
  el.innerHTML='<b>'+d.count+' result(s)</b>';
  d.results.forEach(function(p){
    var dob=p.dob?p.dob.split('T')[0]:'?';
    var dos=p.last_dos?p.last_dos.split('T')[0]:'—';
    el.innerHTML+='<div class="patient"><div class="name">'+p.last_name+', '+p.first_name+'</div>'+
      'DOB: '+dob+' &nbsp;|&nbsp; Sex: '+(p.sex||'?')+'<br>'+
      'Member ID: '+(p.member_id||'—')+'<br>'+
      'Last DOS: '+dos+' &nbsp;|&nbsp; Encounters: '+p.encounter_count+' &nbsp;|&nbsp; Tests: '+p.test_count+
      '</div>';
  });
}
function err(e){document.getElementById('results').innerHTML='<span class="err">'+e.message+'</span>';}
</script>
</body>
</html>`;
