/**
 * ================================================================
 *  REDDIT x HYPERPARSE  -  Google Sheet script  (v10)
 * ================================================================
 *
 *  SETUP (one time, 3 minutes)
 *   1. Sheet > Extensions > Apps Script. Delete the old code, paste
 *      this whole file, click Save.
 *   2. Pick  hyperparseSetup  in the function list > Run > Allow.
 *      A box shows your SECURITY KEY. A blue "Push to Sheet1"
 *      button appears on the New Cases tab.
 *   3. Deploy > New deployment > gear > Web app.
 *      Execute as: Me
 *      Who has access: "Anyone within Ditto"  (or "Anyone" if offered)
 *      > Deploy. Copy the WEB APP URL (ends in /exec).
 *   4. HyperParse > Reddit > Google Sheet: paste URL + key > Connect.
 *      "Anyone within Ditto": HyperParse then shows "Sign in to Google
 *      once" - sign in with your Ditto account in the window. Done.
 *
 *  DAILY USE
 *   - HyperParse: Reddit > Start scraping  ->  new rows land in
 *     "New Cases" (scored, sorted, Ditto rows in green).
 *   - Sheet: click "Push to Sheet1"  ->  rows move to Sheet1 with
 *     today's date + Reviewed box; New Cases is emptied.
 *
 *  GOOD TO KNOW
 *   - Nothing can be read or written without the key. Keep it private.
 *     New key: menu HyperParse > Make a new key.
 *   - Edited this script later? Deploy > Manage deployments > pencil >
 *     Version: New version > Deploy (the URL stays the same).
 *   - Button gone? Menu HyperParse > Add the Push button again.
 *   - The old "Reddit Scraper" menu still works as before.
 * ================================================================
 */

const CONFIG = {
  OUTPUT_SHEET: 'New Cases',
  LEGACY_SHEET: 'reddit',

  TIME_FILTER: 'day',
  USER_AGENT: 'apps-script:reddit-to-sheets:v9 (by u/your_reddit_username)',

  MAX_RUN_MINUTES: 4.5,
  FETCH_POST_DETAILS: false,

  PURGE_AFTER_MONTHS: 6,
  DITTO_HIGHLIGHT_COLOR: '#b7e1cd',
  MOTOR_EXCLUDE: ['car', 'cars', 'vehicle', 'motor', 'bike'],

  // Umbrella phrases — searched inside tracked subs only (never globally)
  UMBRELLA_TERMS: ['health insurance', 'term insurance'],

  PRIORITY: {
    FRESHNESS_MAX: 30,
    FRESHNESS_TAU_HOURS: 18,

    BRAND_DITTO: 25,
    BRAND_COMPETITOR_PLATFORM: 18,
    BRAND_INSURER_PLAN: 12,
    BRAND_GENERIC: 5,
    COMPETITOR_PLATFORMS: [
      'Policybazaar', 'Policy Bazaar', 'InsuranceDekho', 'PolicyX', 'Coverfox',
      'Turtlemint', 'RenewBuy', 'Beshak', 'BimaKavach', 'Onsurity', 'Bajaj Markets',
      'Paytm Insurance', 'Probus Insurance', 'SecureNow', 'Pazcare',
      'Algates Insurance', 'InsuranceSamadhan'
    ],

    INTENT_MAX: 15,
    INTENT_QUESTION: 4,
    INTENT_COMPARISON: 8,
    INTENT_BUYING: 8,
    INTENT_HELP: 4,

    SUB_HIGH: 20,
    SUB_CORE: 12,
    SUB_NICHE: 8,
    SUB_DEFAULT: 6,
    SUBREDDIT_AUTHORITY: {
      high: ['personalfinanceindia', 'IndianPersonalFinance'],
      core: ['HealthInsuranceIndia', 'InsuranceTroubleIndia', 'InsuranceAdviceIndia',
             'MedicalInsuranceIndia', 'TermInsuranceIndia', 'indiahealthinsurance'],
      niche: ['InsuranceQueriesIndia', 'InsuranceGuideIndia', 'HealthInsuranceAMA',
              'InsuranceHelpIndia', 'InsuranceGyaan']
    },

    SPEC_1: 4,
    SPEC_2: 7,
    SPEC_3PLUS: 10
  },

  // Insurance subs — searched for full jargon groups + umbrella phrases
  INCLUDE_SUBREDDITS: [
    'indiahealthinsurance', 'HealthInsuranceIndia', 'InsuranceTroubleIndia',
    'InsuranceAdviceIndia', 'MedicalInsuranceIndia', 'personalfinanceindia',
    'InsuranceQueriesIndia', 'InsuranceGuideIndia', 'HealthInsuranceAMA',
    'InsuranceHelpIndia', 'InsuranceGyaan', 'IndianPersonalFinance', 'TermInsuranceIndia'
  ],

  // Regional/general subs — searched for umbrella phrases ONLY
  REGIONAL_SUBREDDITS: [
    'navimumbai', 'mumbai', 'bangalore', 'india', 'delhi', 'Kerala',
    'TamilNadu', 'bihar', 'Maharashtra', 'Goa', 'karnataka'
  ],

  EXCLUDE_SUBREDDITS: [
    'AusFinance', 'FIREUK', 'remoteworking', 'remotework', 'germany',
    'AskAGerman', 'RemoteJobs', 'GoingToSpain', 'JobsPhilippines', 'AusVisa'
  ],

  GLOBAL_KEYWORDS: [
    'Star Health', 'Star Health & Allied Insurance', 'Niva Bupa', 'Care Health Insurance',
    'Aditya Birla Health Insurance', 'ManipalCigna',
    'HDFC ERGO', 'ICICI Lombard', 'Bajaj Allianz', 'Bajaj General Insurance', 'Tata AIG',
    'SBI General', 'Go Digit', 'Cholamandalam MS', 'Royal Sundaram', 'IFFCO Tokio',
    'Liberty General Insurance', 'Magma HDI', 'Generali Central', 'Future Generali',
    'Galaxy Health Insurance', 'Raheja QBE', 'IndusInd General Insurance', 'Reliance General',
    'Universal Sompo', 'Zuno General Insurance', 'Edelweiss General Insurance',
    'Zurich Kotak General Insurance', 'New India Assurance', 'National Insurance Company',
    'Oriental Insurance', 'United India Insurance', 'Acko General Insurance', 'Acko Insurance',
    'LIC of India', 'LIC India', 'Axis Max Life', 'Max Life Insurance', 'HDFC Life',
    'ICICI Prudential Life', 'SBI Life', 'Bajaj Life Insurance', 'Tata AIA Life',
    'Kotak Mahindra Life', 'Aditya Birla Sun Life', 'PNB MetLife', 'Canara HSBC Life',
    'Ageas Federal Life', 'Aviva Life', 'Bandhan Life', 'Edelweiss Life', 'Zuno Life',
    'Future Generali India Life', 'IndiaFirst Life', 'Pramerica Life', 'Reliance Nippon Life',
    'Sahara India Life', 'Shriram Life', 'Star Union Dai-ichi Life', 'Acko Life Insurance',
    'Go Digit Life Insurance', 'Bharti AXA Life',
    'Policybazaar', 'Policy Bazaar', 'InsuranceDekho', 'Ditto Insurance', 'PolicyX',
    'Coverfox', 'Turtlemint', 'RenewBuy', 'Beshak', 'BimaKavach', 'Onsurity',
    'GoMedii', 'Bajaj Markets', 'Paytm Insurance', 'Probus Insurance', 'SecureNow',
    'Pazcare', 'Algates Insurance', 'InsuranceSamadhan',
    'Optima Restore', 'Optima Secure', 'my:health Suraksha', 'my:health Koti Suraksha',
    'Health Wallet HDFC', 'Easy Health HDFC', 'Arogya Sanjeevani',
    'Family Health Optima', 'Star Comprehensive Insurance Policy', 'Senior Citizens Red Carpet',
    'Young Star Insurance Policy', 'Medi Classic Insurance Policy', 'Diabetes Safe Insurance Policy',
    'Star Health Assure', 'Care Supreme', 'Care Advantage', 'Care Freedom',
    'ReAssure 2.0', 'ReAssure Niva Bupa', 'Aspire Niva Bupa', 'Health Companion Niva Bupa',
    'Activ One MAX', 'Activ Health Platinum', 'ICICI Elevate', 'Health AdvantEdge',
    'Tata AIG MediCare Premier', 'Tata AIG MediCare', 'Bajaj My Health Care', 'Bajaj Health Guard',
    'SBI Arogya Premier', 'SBI Arogya Supreme', 'ManipalCigna ProHealth Protect',
    'ManipalCigna ProHealth Plus', 'Go Digit Health Care Plan', 'Royal Sundaram Lifeline Supreme',
    'National Mediclaim Policy', 'New India Mediclaim Policy', 'New India Premier Mediclaim',
    'Oriental Happy Family Floater', 'United India Individual Mediclaim',
    'Smart Term Plan Plus', 'Saral Jeevan Bima', 'Click 2 Protect Supreme', 'Click 2 Protect Super',
    'iProtect Smart', 'eTouch II', 'Smart Protect Goal', 'eShield Next', 'Smart Shield Plus',
    'LIC Tech Term', 'Jeevan Amar', 'Sampoorna Raksha Supreme', 'Sampoorna Raksha Promise',
    'Maha Raksha Supreme Select', 'Kotak e-Term', 'Mera Term Plan Plus', 'iSelect Star Term Plan',
    'Young Term Plan Canara HSBC', 'DigiShield Plan', 'Flexi Term Bharti AXA',
    'Future Generali Care Plus'
  ],

  HEALTH_TERM_GROUPS: [
    ['mediclaim', 'cashless hospitalization', 'network hospital', 'claim settlement ratio',
     'incurred claim ratio', 'sum insured', 'family floater', 'top-up plan', 'super top-up',
     'no claim bonus'],
    ['waiting period', 'pre-existing disease', 'co-payment', 'room rent limit',
     'restoration benefit', 'day care procedure', 'domiciliary hospitalization', 'OPD cover',
     'critical illness cover', 'health insurance portability'],
    ['free look period', 'AYUSH treatment', 'TPA', 'pre-hospitalization', 'post-hospitalization',
     'deductible', 'IRDAI', 'GMC', 'corporate health insurance', 'group health insurance'],
    ['maternity cover', 'newborn cover', 'bariatric surgery cover', 'modern treatment cover',
     'consumables cover', 'wellness program', 'preventive health checkup', 'cashless everywhere',
     'reimbursement claim', 'solvency ratio'],
    ['mediclaim rejection', 'claim denied', 'claim repudiated', 'hospital cash policy',
     'personal accident cover', 'OPD insurance', 'senior citizen health plan',
     'parents health insurance', 'individual health plan', 'super top up vs top up']
  ],

  TERM_TERM_GROUPS: [
    ['sum assured', 'death benefit', 'return of premium', 'ROP plan', 'level term cover',
     'increasing cover', 'decreasing cover', 'waiver of premium', 'accidental death benefit',
     'accidental disability rider'],
    ['terminal illness benefit', 'life cover', 'pure term plan', 'term plan tax benefit',
     '80C', '80D', 'riders', 'premium payment term', 'policy term', 'life stage benefit'],
    ['surrender value', 'nominee', 'underwriting', 'medical test for insurance',
     'smoker non-smoker premium', 'group term insurance', 'credit life insurance',
     'mortgage protection plan', 'income replacement plan', 'child term plan'],
    ['whole life term plan', 'claim rejected term insurance', 'term insurance for self employed',
     'term insurance for NRI', 'lapsed policy revival', 'grace period', 'exclusion clause',
     'suicide clause', 'term insurance vs ULIP', 'term insurance vs endowment'],
    ['saral jeevan bima', "married women's property act", 'MWPA', 'keyman insurance']
  ]
};

const DITTO_SET_ = new Set(['ditto', 'ditto insurance']);
const PLATFORM_SET_ = new Set(CONFIG.PRIORITY.COMPETITOR_PLATFORMS.map(s => s.toLowerCase()));
const GENERIC_SET_ = new Set(
  [].concat(...CONFIG.HEALTH_TERM_GROUPS, ...CONFIG.TERM_TERM_GROUPS, CONFIG.UMBRELLA_TERMS)
    .map(s => s.toLowerCase())
);

const NUM_COLS = 12; // A..L (both tabs)

// ============================================================
// CUSTOM MENU
// ============================================================
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Reddit Scraper')
    .addItem('Force scrape now', 'forceScrapeNow')
    .addItem('Clean up New Cases (no crawl)', 'cleanupNewCasesNow')
    .addItem('Recompute priorities only', 'recomputePrioritiesNow')
    .addToUi();
  ui.createMenu('HyperParse')
    .addItem('Push New Cases to Sheet1', 'pushNewCasesToSheet1')
    .addSeparator()
    .addItem('Set up / show connection key', 'hyperparseSetup')
    .addItem('Make a new key (old one stops working)', 'hyperparseNewKey')
    .addItem('Add the Push button again', 'hyperparseAddButton')
    .addToUi();
}

function forceScrapeNow() {
  run();
  SpreadsheetApp.getUi().alert('Scrape complete.');
}

/** Zero-network: recompute today's + prior rows, archive prior (with scores), sort, highlight. */
function cleanupNewCasesNow() {
  const sh = ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  ensureLegacySheet_(CONFIG.LEGACY_SHEET);
  recomputeAllPriorities_(sh);
  partitionByPostedToday_(sh);
  sortByPriority_(sh);
  applyDittoHighlight_(sh);
  SpreadsheetApp.getUi().alert("New Cases cleaned: only today's posts kept (archived rows keep their score).");
}

function recomputePrioritiesNow() {
  const sh = ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  recomputeAllPriorities_(sh);
  sortByPriority_(sh);
  applyDittoHighlight_(sh);
  SpreadsheetApp.getUi().alert('Priority scores recomputed.');
}

// ============================================================
// SETUP — run once. Removes any old auto-trigger; installs NONE.
// ============================================================
function setup() {
  ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  ensureLegacySheet_(CONFIG.LEGACY_SHEET);
  const triggers = ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'run');
  triggers.forEach(t => ScriptApp.deleteTrigger(t));
}

// ============================================================
// MAIN ENTRY POINT (force scrape only)
// ============================================================
function run() {
  const deadline = Date.now() + Math.round(CONFIG.MAX_RUN_MINUTES * 60 * 1000);

  const outSheet = ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  ensureLegacySheet_(CONFIG.LEGACY_SHEET);

  const rowsToAppend = collectRows_(deadline);

  if (rowsToAppend.length) {
    const startRow = outSheet.getLastRow() + 1;
    outSheet.getRange(startRow, 1, rowsToAppend.length, NUM_COLS).setValues(rowsToAppend);
  }

  // Recompute FIRST so every row (today + prior) has a current score,
  // THEN archive prior-day rows (carrying that score) into reddit.
  recomputeAllPriorities_(outSheet);
  partitionByPostedToday_(outSheet);
  sortByPriority_(outSheet);
  purgeOldRows_(outSheet);
  applyDittoHighlight_(outSheet);
}

/** Fetch Reddit RSS (+ comments) and return new 12-col rows not seen in any tab. */
function collectRows_(deadline) {
  const existing = readExistingIdsAcrossTabs_([CONFIG.LEGACY_SHEET, CONFIG.OUTPUT_SHEET, HP.ARCHIVE_SHEET]);

  const matchKeywords = buildMatchKeywords_();
  const queries = buildSearchQueries_();

  const entries = [];
  for (const q of queries) {
    if (Date.now() > deadline) break;
    entries.push(...fetchRssEntries_(q.url, q.scope, q.subreddit));
  }

  const seenInThisRun = new Map();
  for (const e of entries) {
    if (!e.post_id) continue;
    if (isSubredditExcluded_(e.subreddit)) continue;
    if (!seenInThisRun.has(e.post_id)) seenInThisRun.set(e.post_id, e);
  }

  const rowsToAppend = [];

  for (const e of seenInThisRun.values()) {
    if (Date.now() > deadline) break;
    if (existing.has(e.post_id)) continue;

    const blob = `${e.title}\n${e.content_plain || ''}`;
    if (isMotorText_(blob)) continue;

    let matched = dedupeDitto_(getMatchedTerms_(blob, matchKeywords));
    if (matched.length === 0) continue;

    const details = CONFIG.FETCH_POST_DETAILS ? fetchPostDetails_(e.post_id, CONFIG.USER_AGENT) : null;
    const createdIso = details && details.created_utc
      ? toIST_(details.created_utc)
      : (e.created_utc ? toIST_(e.created_utc) : '');

    rowsToAppend.push([
      e.post_id, createdIso,
      e.subreddit || (details && details.subreddit) || '',
      e.title || (details && details.title) || '',
      e.author || (details && details.author) || '',
      e.permalink || e.link || (details && ('https://www.reddit.com' + details.permalink)) || '',
      matched.join(', '), 'post',
      details ? details.score : '', details ? details.num_comments : '',
      '', ''
    ]);
    existing.add(e.post_id);

    const comments = fetchCommentsForPost_(e.post_id, CONFIG.USER_AGENT);
    for (const c of comments) {
      if (!c.body) continue;
      if (isMotorText_(c.body)) continue;
      let matchedC = dedupeDitto_(getMatchedTerms_(c.body, matchKeywords));
      if (matchedC.length === 0) continue;

      const cid = `${e.post_id}_${c.id}`;
      if (existing.has(cid)) continue;

      rowsToAppend.push([
        cid, toIST_(c.created_utc), e.subreddit || '', '(comment)', c.author || '',
        `https://www.reddit.com${c.permalink}`, matchedC.join(', '), 'comment',
        c.score || '', '', '', ''
      ]);
      existing.add(cid);
    }
  }
  return rowsToAppend;
}

// ============================================================
// PARTITION (bulk): keep today's posts in New Cases; move the rest (WITH their
// priority_score/breakdown) into reddit. Keyed off created_utc (col B).
// ============================================================
function partitionByPostedToday_(newSheet) {
  const last = newSheet.getLastRow();
  if (last < 2) return;
  const today = todayIstYmd_();
  const n = last - 1;
  const data = newSheet.getRange(2, 1, n, NUM_COLS).getValues(); // A..L incl fresh K/L

  const keep = [];
  const archive = [];
  for (let i = 0; i < n; i++) {
    const ymd = toYmdIst_(data[i][1]); // col B = created_utc
    if (ymd === today) keep.push(data[i]);
    else archive.push(data[i]); // full 12-col row -> reddit keeps score/breakdown
  }

  if (archive.length) {
    const reddit = ensureLegacySheet_(CONFIG.LEGACY_SHEET);
    const start = reddit.getLastRow() + 1;
    reddit.getRange(start, 1, archive.length, NUM_COLS).setValues(archive);
  }

  newSheet.getRange(2, 1, n, NUM_COLS).clearContent();
  newSheet.getRange(2, 1, n, NUM_COLS).setBackground(null);
  if (keep.length) {
    newSheet.getRange(2, 1, keep.length, NUM_COLS).setValues(keep);
  }
}

// ============================================================
// PRIORITY SCORING
// ============================================================
function computePriority_(row, nowMs) {
  const fresh  = freshnessPoints_(row[1], nowMs);
  const brand  = brandPoints_(row[6]);
  const intent = intentPoints_(row[3], row[7]);
  const sub    = subredditPoints_(row[2]);
  const multi  = specificityPoints_(row[6]);
  const total = Math.round(fresh + brand + intent + sub + multi);
  const breakdown = `F${Math.round(fresh)} B${brand} I${intent} S${sub} M${multi}`;
  return { total, breakdown };
}

function freshnessPoints_(created, nowMs) {
  const P = CONFIG.PRIORITY;
  const d = parseIstToDate_(created);
  if (!d) return 0;
  let ageH = (nowMs - d.getTime()) / 3600000;
  if (ageH < 0) ageH = 0;
  return P.FRESHNESS_MAX * Math.exp(-ageH / P.FRESHNESS_TAU_HOURS);
}

function brandPoints_(matchedTermsStr) {
  const P = CONFIG.PRIORITY;
  const terms = String(matchedTermsStr || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  if (!terms.length) return 0;
  let pts = 0;
  if (terms.some(t => DITTO_SET_.has(t)))    pts = Math.max(pts, P.BRAND_DITTO);
  if (terms.some(t => PLATFORM_SET_.has(t)))  pts = Math.max(pts, P.BRAND_COMPETITOR_PLATFORM);
  if (terms.some(t => !DITTO_SET_.has(t) && !PLATFORM_SET_.has(t) && !GENERIC_SET_.has(t))) {
    pts = Math.max(pts, P.BRAND_INSURER_PLAN);
  }
  if (terms.some(t => GENERIC_SET_.has(t)))   pts = Math.max(pts, P.BRAND_GENERIC);
  return pts;
}

function intentPoints_(title, sourceType) {
  const P = CONFIG.PRIORITY;
  if (sourceType === 'comment') return 0;
  const t = String(title || '').toLowerCase();
  if (!t) return 0;
  let pts = 0;
  if (t.indexOf('?') !== -1) pts += P.INTENT_QUESTION;
  if (/\bvs\b|\bor\b|compare|comparison|better|difference between/.test(t)) pts += P.INTENT_COMPARISON;
  if (/\bbuy\b|\bbest\b|recommend|suggest|which plan|which policy|should i|looking for|planning|worth/.test(t)) pts += P.INTENT_BUYING;
  if (/\bhelp\b|advice|advise|confused|guidance|suggestion/.test(t)) pts += P.INTENT_HELP;
  return Math.min(pts, P.INTENT_MAX);
}

function subredditPoints_(subreddit) {
  const P = CONFIG.PRIORITY;
  const s = String(subreddit || '').toLowerCase();
  if (!s) return P.SUB_DEFAULT;
  const A = P.SUBREDDIT_AUTHORITY;
  if (A.high.some(x => x.toLowerCase() === s))  return P.SUB_HIGH;
  if (A.core.some(x => x.toLowerCase() === s))  return P.SUB_CORE;
  if (A.niche.some(x => x.toLowerCase() === s)) return P.SUB_NICHE;
  return P.SUB_DEFAULT;
}

function specificityPoints_(matchedTermsStr) {
  const P = CONFIG.PRIORITY;
  const terms = String(matchedTermsStr || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  const seen = new Set();
  for (const t of terms) {
    if (GENERIC_SET_.has(t)) continue;
    seen.add(t);
  }
  const n = seen.size;
  if (n >= 3) return P.SPEC_3PLUS;
  if (n === 2) return P.SPEC_2;
  if (n === 1) return P.SPEC_1;
  return 0;
}

function recomputeAllPriorities_(sh) {
  const last = sh.getLastRow();
  if (last < 2) return;
  const n = last - 1;
  const data = sh.getRange(2, 1, n, 10).getValues();
  const createdStrs = sh.getRange(2, 2, n, 1).getDisplayValues();
  const nowMs = Date.now();
  const out = [];
  for (let i = 0; i < n; i++) {
    const row = data[i];
    row[1] = createdStrs[i][0];
    const { total, breakdown } = computePriority_(row, nowMs);
    out.push([total, breakdown]);
  }
  sh.getRange(2, 11, n, 2).setValues(out);
}

function parseIstToDate_(s) {
  if (s instanceof Date) return s;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(String(s || ''));
  if (!m) return null;
  const utcMs = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) - (5.5 * 3600 * 1000);
  return new Date(utcMs);
}

// ============================================================
// DATE HELPERS
// ============================================================
function todayIstYmd_() {
  return Utilities.formatDate(new Date(), 'Asia/Kolkata', 'yyyy-MM-dd');
}

function toYmdIst_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, 'Asia/Kolkata', 'yyyy-MM-dd');
  const s = String(v || '').trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  const d = new Date(s);
  if (!isNaN(d.getTime())) return Utilities.formatDate(d, 'Asia/Kolkata', 'yyyy-MM-dd');
  return '';
}

// ============================================================
// SHEET HELPERS
// ============================================================
function ensureSheet_(name, createHeaders) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (createHeaders || sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, NUM_COLS).setValues([HEADERS_()]);
  }
  return sh;
}

/** reddit archive tab now uses the SAME 12-col header so archived scores are kept. */
function ensureLegacySheet_(name) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  sh.getRange(1, 1, 1, NUM_COLS).setValues([HEADERS_()]);
  return sh;
}

function HEADERS_() {
  return [
    'post_id', 'created_utc', 'subreddit', 'title', 'author', 'permalink',
    'matched_terms', 'source_type', 'score', 'num_comments',
    'priority_score', 'priority_breakdown'
  ];
}

function readIdsFromSheet_(name) {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(name);
  if (!sh) return [];
  const last = sh.getLastRow();
  if (last < 2) return [];
  // Sheet1 starts with a "Date" column, so its post_id is in column B.
  const col = name === HP.ARCHIVE_SHEET ? 2 : 1;
  return sh.getRange(2, col, last - 1, 1).getValues().flat()
    .filter(Boolean).map(String);
}

function readExistingIdsAcrossTabs_(sheetNames) {
  const set = new Set();
  sheetNames.forEach(n => readIdsFromSheet_(n).forEach(id => set.add(id)));
  return set;
}

function sortByPriority_(sh) {
  const last = sh.getLastRow();
  if (last < 3) return;
  sh.getRange(2, 1, last - 1, NUM_COLS).sort([
    { column: 11, ascending: false },
    { column: 2, ascending: false }
  ]);
}

function purgeOldRows_(sh) {
  const last = sh.getLastRow();
  if (last < 2) return;
  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - CONFIG.PURGE_AFTER_MONTHS);
  const values = sh.getRange(2, 2, last - 1, 1).getValues();
  const rowsToDelete = [];
  for (let i = 0; i < values.length; i++) {
    const raw = values[i][0];
    if (!raw) continue;
    const d = new Date(raw);
    if (isNaN(d.getTime())) continue;
    if (d < cutoff) rowsToDelete.push(i + 2);
  }
  for (let i = rowsToDelete.length - 1; i >= 0; i--) sh.deleteRow(rowsToDelete[i]);
  if (rowsToDelete.length) {
    Logger.log(`Purged ${rowsToDelete.length} row(s) older than ${CONFIG.PURGE_AFTER_MONTHS} months.`);
  }
}

function applyDittoHighlight_(sh) {
  const last = sh.getLastRow();
  if (last < 2) return;
  const numRows = last - 1;
  const matchedCol = sh.getRange(2, 7, numRows, 1).getValues();
  const bg = [];
  for (let i = 0; i < numRows; i++) {
    const g = String(matchedCol[i][0] || '');
    const color = /\bditto\b/i.test(g) ? CONFIG.DITTO_HIGHLIGHT_COLOR : null;
    bg.push(new Array(NUM_COLS).fill(color));
  }
  sh.getRange(2, 1, numRows, NUM_COLS).setBackgrounds(bg);
}

// ============================================================
// QUERY BUILDING
//  Order: 1) global  2) umbrella in ALL tracked subs (incl regional)
//         3) jargon groups in insurance subs
// ============================================================
function buildSearchQueries_() {
  const queries = [];
  const params = '&sort=new&t=' + encodeURIComponent(CONFIG.TIME_FILTER);

  // 1) Global brand/plan search
  const globalChunks = chunkArray_(CONFIG.GLOBAL_KEYWORDS, 12);
  globalChunks.forEach(chunk => {
    const q = '(' + chunk.map(quoteIfNeeded_).join(' OR ') + ')';
    queries.push({
      url: `https://www.reddit.com/search.rss?q=${encodeURIComponent(q)}${params}`,
      scope: 'global', subreddit: null
    });
  });

  // 2) Umbrella phrases in every tracked sub (insurance + regional) — high value, run first
  const umbrellaQ = '(' + CONFIG.UMBRELLA_TERMS.map(quoteIfNeeded_).join(' OR ') + ')';
  const allTrackedSubs = CONFIG.INCLUDE_SUBREDDITS.concat(CONFIG.REGIONAL_SUBREDDITS);
  allTrackedSubs.forEach(sr => {
    queries.push({
      url: `https://www.reddit.com/r/${encodeURIComponent(sr)}/search.rss?q=${encodeURIComponent(umbrellaQ)}&restrict_sr=on${params}`,
      scope: 'subreddit', subreddit: sr
    });
  });

  // 3) Full jargon groups in insurance subs only
  const jargonGroups = CONFIG.HEALTH_TERM_GROUPS.concat(CONFIG.TERM_TERM_GROUPS);
  CONFIG.INCLUDE_SUBREDDITS.forEach(sr => {
    jargonGroups.forEach(group => {
      const q = '(' + group.map(quoteIfNeeded_).join(' OR ') + ')';
      queries.push({
        url: `https://www.reddit.com/r/${encodeURIComponent(sr)}/search.rss?q=${encodeURIComponent(q)}&restrict_sr=on${params}`,
        scope: 'subreddit', subreddit: sr
      });
    });
  });

  return queries;
}

function quoteIfNeeded_(term) { return term.indexOf(' ') !== -1 ? `"${term}"` : term; }

function chunkArray_(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

function buildMatchKeywords_() {
  return CONFIG.GLOBAL_KEYWORDS
    .concat(...CONFIG.HEALTH_TERM_GROUPS)
    .concat(...CONFIG.TERM_TERM_GROUPS)
    .concat(CONFIG.UMBRELLA_TERMS)
    .concat(['Ditto']);
}

// ============================================================
// EXCLUSION HELPERS
// ============================================================
function isSubredditExcluded_(subreddit) {
  const s = (subreddit || '').toLowerCase();
  if (!s) return false;
  if (CONFIG.EXCLUDE_SUBREDDITS.map(x => x.toLowerCase()).indexOf(s) !== -1) return true;
  return CONFIG.MOTOR_EXCLUDE.some(t => s.indexOf(t) !== -1);
}

function isMotorText_(text) {
  for (const t of CONFIG.MOTOR_EXCLUDE) {
    if (new RegExp(`\\b${escapeRegex_(t)}\\b`, 'i').test(text)) return true;
  }
  return false;
}

function dedupeDitto_(arr) {
  const hasCompound = arr.some(t => t !== 'Ditto' && /ditto/i.test(t));
  return hasCompound ? arr.filter(t => t !== 'Ditto') : arr;
}

// ============================================================
// FETCHING
// ============================================================
function fetchRssEntries_(url, scope, restrictedSubreddit) {
  const options = { muteHttpExceptions: true, headers: { 'User-Agent': CONFIG.USER_AGENT } };
  const res = UrlFetchApp.fetch(url, options);
  if (res.getResponseCode() !== 200) return [];
  const parsed = parseAtomOrRss_(res.getContentText(), url);
  if (scope === 'subreddit' && restrictedSubreddit) {
    parsed.forEach(e => { if (!e.subreddit) e.subreddit = restrictedSubreddit; });
  }
  return parsed;
}

function parseAtomOrRss_(xmlText, sourceUrl) {
  const doc = XmlService.parse(xmlText);
  const root = doc.getRootElement();
  const nsAtom = XmlService.getNamespace('http://www.w3.org/2005/Atom');
  let entries = [];
  if (root.getName() === 'feed') {
    const children = root.getChildren('entry', nsAtom);
    for (const e of children) {
      const title = getText_(e, 'title', nsAtom);
      const id = getText_(e, 'id', nsAtom);
      const updated = getText_(e, 'updated', nsAtom);
      const authorName = (() => {
        const author = e.getChild('author', nsAtom);
        return author ? getText_(author, 'name', nsAtom) : '';
      })();
      let link = '';
      const linkEl = e.getChild('link', nsAtom);
      if (linkEl) {
        const href = linkEl.getAttribute('href');
        if (href) link = href.getValue();
      }
      const contentHtml = getText_(e, 'content', nsAtom) || getText_(e, 'summary', nsAtom) || '';
      const contentPlain = stripHtml_(contentHtml);
      const { subreddit, postId } = extractFromLink_(link);
      entries.push({
        title, id_raw: id, post_id: postId || id, created_utc: updated, author: authorName,
        link, permalink: link, content_plain: contentPlain, subreddit, source_url: sourceUrl
      });
    }
  } else if (root.getName() === 'rss') {
    const channel = root.getChild('channel');
    if (channel) {
      const items = channel.getChildren('item');
      for (const it of items) {
        const title = childText_(it, 'title');
        const link = childText_(it, 'link');
        const pub = childText_(it, 'pubDate');
        const content = childText_(it, 'description') || '';
        const { subreddit, postId } = extractFromLink_(link);
        entries.push({
          title, id_raw: link, post_id: postId || link, created_utc: pub, author: '',
          link, permalink: link, content_plain: stripHtml_(content), subreddit, source_url: sourceUrl
        });
      }
    }
  }
  return entries;
}

function fetchCommentsForPost_(postId, userAgent) {
  if (!postId) return [];
  const url = `https://www.reddit.com/comments/${postId}.json?limit=100&sort=new`;
  const options = { muteHttpExceptions: true, headers: { 'User-Agent': userAgent } };
  try {
    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() !== 200) return [];
    const data = JSON.parse(res.getContentText());
    if (!data[1] || !data[1].data) return [];
    return data[1].data.children.filter(c => c.kind === 't1').map(c => c.data);
  } catch (err) {
    Logger.log('Error fetching comments: ' + err);
    return [];
  }
}

function fetchPostDetails_(postId, userAgent) {
  if (!postId) return null;
  const url = `https://www.reddit.com/comments/${postId}.json?limit=1`;
  const options = { muteHttpExceptions: true, headers: { 'User-Agent': userAgent } };
  try {
    const res = UrlFetchApp.fetch(url, options);
    if (res.getResponseCode() !== 200) return null;
    const data = JSON.parse(res.getContentText());
    if (!data[0] || !data[0].data) return null;
    const post = data[0].data.children.find(c => c.kind === 't3');
    return post ? post.data : null;
  } catch (err) {
    Logger.log('Error fetching post details: ' + err);
    return null;
  }
}

// ============================================================
// SMALL UTILITIES
// ============================================================
function toIST_(utcSecondsOrDate) {
  let dateObj;
  if (typeof utcSecondsOrDate === 'number') dateObj = new Date(utcSecondsOrDate * 1000);
  else dateObj = new Date(utcSecondsOrDate);
  return Utilities.formatDate(dateObj, "Asia/Kolkata", "yyyy-MM-dd HH:mm:ss");
}

function getText_(parent, name, ns) {
  const el = parent.getChild(name, ns);
  return el ? el.getText() : '';
}

function childText_(parent, name) {
  const el = parent.getChild(name);
  return el ? el.getText() : '';
}

function stripHtml_(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function extractFromLink_(link) {
  const m = /\/r\/([^/]+)\/comments\/([a-z0-9]{5,8})/i.exec(link || '');
  return { subreddit: m ? m[1] : '', postId: m ? m[2] : '' };
}

function escapeRegex_(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

function getMatchedTerms_(text, keywords) {
  const found = [];
  for (const k of keywords) {
    if (new RegExp(`\\b${escapeRegex_(k)}\\b`, 'i').test(text)) found.push(k);
  }
  return found;
}


// ============================================================
// HYPERPARSE — desktop-app connection + "Push to Sheet1" button
// ------------------------------------------------------------
// Setup steps: see the top of this file.
// The key is the lock: without it nobody can read or write this sheet through the URL.
// ============================================================
const HP = {
  ARCHIVE_SHEET: 'Sheet1',
  KEY_PROP: 'HYPERPARSE_KEY',
  BUTTON_FN: 'pushNewCasesToSheet1',
  MAX_ROWS_PER_PUSH: 2000
};

function SHEET1_HEADERS_() {
  return ['Date'].concat(HEADERS_(), ['Links added to the thread', 'Reviewed']);
}

// ---------------- Web App entry points ----------------
function doGet() {
  return hpJson_({ ok: true, app: 'HyperParse Reddit sheet', note: 'Send data with POST and your key.' });
}

function doPost(e) {
  let req;
  try {
    req = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return hpJson_({ ok: false, code: 'bad_request', error: 'The request was not valid JSON.' });
  }
  const key = PropertiesService.getScriptProperties().getProperty(HP.KEY_PROP);
  if (!key) {
    return hpJson_({ ok: false, code: 'no_key',
      error: 'This sheet has no key yet. Open the sheet and run HyperParse > Set up.' });
  }
  if (!hpSafeEqual_(String(req.key || ''), key)) {
    return hpJson_({ ok: false, code: 'bad_key', error: 'Wrong security key.' });
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(90 * 1000)) {
    return hpJson_({ ok: false, code: 'busy', error: 'The sheet is busy. Try again in a minute.' });
  }
  try {
    switch (req.action) {
      case 'ping':   return hpJson_(hpPing_());
      case 'ids':    return hpJson_({ ok: true, ids: Array.from(hpAllIds_()) });
      case 'push':   return hpJson_(hpPush_(req.rows || []));
      case 'scrape': return hpJson_(hpRemoteScrape_());
      default:       return hpJson_({ ok: false, code: 'bad_action', error: 'Unknown action.' });
    }
  } catch (err) {
    return hpJson_({ ok: false, code: 'error', error: String((err && err.message) || err) });
  } finally {
    lock.releaseLock();
  }
}

function hpPing_() {
  const ss = SpreadsheetApp.getActive();
  const nc = ss.getSheetByName(CONFIG.OUTPUT_SHEET);
  return {
    ok: true,
    sheet: ss.getName(),
    new_cases: nc ? Math.max(0, nc.getLastRow() - 1) : 0,
    sheet1: hpLastIdRow_(ss.getSheetByName(HP.ARCHIVE_SHEET)) - 1
  };
}

function hpAllIds_() {
  return readExistingIdsAcrossTabs_([CONFIG.LEGACY_SHEET, CONFIG.OUTPUT_SHEET, HP.ARCHIVE_SHEET]);
}

/** Rows from HyperParse -> New Cases. Skips anything already in New Cases, reddit or Sheet1. */
function hpPush_(rows) {
  if (!Array.isArray(rows)) return { ok: false, code: 'bad_rows', error: 'rows must be a list.' };
  if (rows.length > HP.MAX_ROWS_PER_PUSH) {
    return { ok: false, code: 'too_many', error: 'Send at most ' + HP.MAX_ROWS_PER_PUSH + ' rows at a time.' };
  }
  const sh = ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  ensureLegacySheet_(CONFIG.LEGACY_SHEET);
  const existing = hpAllIds_();
  const headers = HEADERS_();
  const out = [];
  let skipped = 0;

  for (const r of rows) {
    const arr = Array.isArray(r) ? r.slice(0, NUM_COLS) : headers.map(h => (r || {})[h]);
    while (arr.length < NUM_COLS) arr.push('');
    const id = String(arr[0] || '').trim();
    if (!/^[A-Za-z0-9_]{3,40}$/.test(id) || existing.has(id)) { skipped++; continue; }
    existing.add(id);
    out.push(arr.map(hpCell_));
  }

  if (out.length) {
    sh.getRange(sh.getLastRow() + 1, 1, out.length, NUM_COLS).setValues(out);
    recomputeAllPriorities_(sh);
    sortByPriority_(sh);
    applyDittoHighlight_(sh);
  }
  return { ok: true, added: out.length, skipped: skipped, new_cases: Math.max(0, sh.getLastRow() - 1) };
}

/** Backup path: run the sheet's own Reddit search (Google servers) without archiving rows. */
function hpRemoteScrape_() {
  const deadline = Date.now() + Math.round(CONFIG.MAX_RUN_MINUTES * 60 * 1000);
  const sh = ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  ensureLegacySheet_(CONFIG.LEGACY_SHEET);
  const rows = collectRows_(deadline);
  if (rows.length) {
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, NUM_COLS).setValues(rows.map(r => r.map(hpCell_)));
  }
  recomputeAllPriorities_(sh);
  sortByPriority_(sh);
  applyDittoHighlight_(sh);
  return { ok: true, added: rows.length, new_cases: Math.max(0, sh.getLastRow() - 1) };
}

// ---------------- Push New Cases -> Sheet1 (the button) ----------------
function pushNewCasesToSheet1() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(60 * 1000)) {
    SpreadsheetApp.getActive().toast('The sheet is busy (a push is running). Try again in a minute.', 'HyperParse', 6);
    return;
  }
  let res;
  try {
    res = hpMoveToSheet1_();
  } finally {
    lock.releaseLock();
  }
  let msg;
  if (!res.total) msg = 'New Cases is empty - nothing to push.';
  else if (res.moved) msg = 'Pushed ' + res.moved + ' row(s) to Sheet1.' +
    (res.skipped ? ' ' + res.skipped + ' were already in Sheet1.' : '');
  else msg = 'All ' + res.skipped + ' row(s) were already in Sheet1. New Cases is now empty.';
  SpreadsheetApp.getActive().toast(msg, 'HyperParse', 8);
}

function hpMoveToSheet1_() {
  const ss = SpreadsheetApp.getActive();
  const nc = ss.getSheetByName(CONFIG.OUTPUT_SHEET);
  if (!nc || nc.getLastRow() < 2) return { total: 0, moved: 0, skipped: 0 };

  const n = nc.getLastRow() - 1;
  const range = nc.getRange(2, 1, n, NUM_COLS);
  const values = range.getValues();
  const shown = range.getDisplayValues();      // keeps created_utc exactly as shown
  const s1 = hpEnsureSheet1_();
  const have = new Set(readIdsFromSheet_(HP.ARCHIVE_SHEET));
  const today = Utilities.formatDate(new Date(), 'Asia/Kolkata', 'yyyy-MM-dd');

  const out = [];
  let total = 0, skipped = 0;
  for (let i = 0; i < n; i++) {
    const id = String(values[i][0] || '').trim();
    if (!id) continue;
    total++;
    if (have.has(id)) { skipped++; continue; }
    have.add(id);
    const row = values[i].slice();
    row[1] = shown[i][1];
    out.push([today].concat(row.map(hpCell_), ['', false]));
  }

  if (out.length) {
    const start = hpLastIdRow_(s1) + 1;
    const need = start + out.length - 1;
    if (need > s1.getMaxRows()) s1.insertRowsAfter(s1.getMaxRows(), need - s1.getMaxRows());
    const width = SHEET1_HEADERS_().length;
    s1.getRange(start, 1, out.length, width).setValues(out);
    s1.getRange(start, width, out.length, 1).insertCheckboxes();
    s1.getRange(start, 1, out.length, width).setBackground(null);
  }

  range.clearContent();
  range.setBackground(null);
  return { total: total, moved: out.length, skipped: skipped };
}

function hpEnsureSheet1_() {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(HP.ARCHIVE_SHEET);
  if (!sh) sh = ss.insertSheet(HP.ARCHIVE_SHEET);
  const headers = SHEET1_HEADERS_();
  const cur = sh.getRange(1, 1, 1, headers.length).getValues()[0];
  if (cur.every(v => v === '' || v === null)) {
    sh.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  return sh;
}

/** Last row that has a post_id in Sheet1 (column B). Checkbox-only rows don't count. */
function hpLastIdRow_(sh) {
  if (!sh) return 1;
  const last = sh.getLastRow();
  if (last < 2) return 1;
  const ids = sh.getRange(2, 2, last - 1, 1).getValues();
  for (let i = ids.length - 1; i >= 0; i--) {
    if (String(ids[i][0] || '').trim()) return i + 2;
  }
  return 1;
}

// ---------------- setup, key and button ----------------
function hyperparseSetup() {
  ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  ensureLegacySheet_(CONFIG.LEGACY_SHEET);
  hpEnsureSheet1_();
  const props = PropertiesService.getScriptProperties();
  let key = props.getProperty(HP.KEY_PROP);
  if (!key) {
    key = hpMakeKey_();
    props.setProperty(HP.KEY_PROP, key);
  }
  hyperparseAddButton(true);
  hpShowKey_(key, 'HyperParse is set up');
}

function hyperparseNewKey() {
  const ui = SpreadsheetApp.getUi();
  const ok = ui.alert('Make a new key?',
    'The old key stops working right away. You will need to paste the new key into HyperParse.',
    ui.ButtonSet.OK_CANCEL);
  if (ok !== ui.Button.OK) return;
  const key = hpMakeKey_();
  PropertiesService.getScriptProperties().setProperty(HP.KEY_PROP, key);
  hpShowKey_(key, 'New key made');
}

function hyperparseAddButton(quiet) {
  const sh = ensureSheet_(CONFIG.OUTPUT_SHEET, true);
  sh.getImages().forEach(img => {
    try { if (img.getScript() === HP.BUTTON_FN) img.remove(); } catch (e) {}
  });
  const blob = Utilities.newBlob(Utilities.base64Decode(HP_BUTTON_PNG_), 'image/png', 'push.png');
  const img = sh.insertImage(blob, NUM_COLS + 2, 1, 0, 2);
  img.assignScript(HP.BUTTON_FN);
  img.setAltTextTitle('Push to Sheet1');
  img.setWidth(HP_BUTTON_W_).setHeight(HP_BUTTON_H_);
  if (quiet !== true) SpreadsheetApp.getActive().toast('Push button added to New Cases.', 'HyperParse', 5);
}

function hpShowKey_(key, title) {
  let url = '';
  try { url = ScriptApp.getService().getUrl() || ''; } catch (e) {}
  const deployed = /\/exec$/.test(url);
  const box = 'width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #E4E4E7;' +
              'border-radius:12px;font:13px Consolas,monospace';
  const html = HtmlService.createHtmlOutput(
    '<div style="font-family:Inter,Arial,sans-serif;font-size:14px;line-height:20px;color:#3F3F46">' +
    '<p style="margin:0 0 8px"><b style="color:#18181B">Security key</b></p>' +
    '<input readonly onclick="this.select()" value="' + key + '" style="' + box + '">' +
    '<p style="margin:16px 0 8px"><b style="color:#18181B">Web app URL</b></p>' +
    (deployed
      ? '<input readonly onclick="this.select()" value="' + url + '" style="' + box + '">'
      : '<div style="padding:10px 12px;background:#FBF2CA;border-radius:12px">Not deployed yet. ' +
        'Deploy &gt; New deployment &gt; Web app &gt; Execute as <b>Me</b>, Who has access <b>Anyone</b> ' +
        '&gt; Deploy. Copy the URL that ends in <b>/exec</b>.</div>') +
    '<p style="margin:16px 0 0">In HyperParse pick <b>Reddit</b> &gt; <b>Google Sheet</b>, paste the URL ' +
    'and the key, then press <b>Connect</b>. Keep the key private.</p></div>'
  ).setWidth(460).setHeight(330);
  SpreadsheetApp.getUi().showModalDialog(html, title);
}

function hpMakeKey_() {
  return ('hp_' + Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
}

// ---------------- small helpers ----------------
function hpJson_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function hpSafeEqual_(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Text that starts with = + - @ would run as a formula: store it as plain text. */
function hpCell_(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number' || typeof v === 'boolean' || v instanceof Date) return v;
  let s = String(v);
  if (s.length > 49000) s = s.slice(0, 49000);
  return /^[=+\-@]/.test(s) ? "'" + s : s;
}

// "Push to Sheet1" button picture (made by HyperParse)
const HP_BUTTON_W_ = 202;
const HP_BUTTON_H_ = 52;
const HP_BUTTON_PNG_ = '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';
