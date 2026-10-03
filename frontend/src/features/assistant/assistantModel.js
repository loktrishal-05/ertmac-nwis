// NWIS in-app assistant: pure, testable logic. It only helps with using eRTMAC-NWIS.
// Guardrails run before any model is involved: injection attempts, operational-control requests and off-topic
// questions are refused deterministically, in the user's language.

export const LANGS = { en: 'English', hi: 'Hindi', ta: 'Tamil' }
export const SPEECH_LOCALE = { en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN' }

// Devanagari or Tamil script decides the reply language; Latin text follows the UI language.
export const detectLanguage = (text, uiLanguage = 'en') =>
  /[ऀ-ॿ]/.test(text) ? 'hi' : /[஀-௿]/.test(text) ? 'ta' : (LANGS[uiLanguage] ? uiLanguage : 'en')

const INJECTION = /(ignore|disregard|forget)\s+(all\s+|the\s+|your\s+|previous\s+|above\s+)*(instructions|rules|prompt)|system\s*prompt|you\s+are\s+now|act\s+as|pretend|jailbreak|developer\s+mode|reveal\s+(your|the)\s+(prompt|instructions)/i
const CONTROL = /\b(increase|decrease|raise|lower|change|set|adjust|reduce|stop|start|shut|open|close)\b.{0,40}\b(mud\s*weight|rpm|wob|weight\s+on\s+bit|pump|flow\s*rate|spp|drilling\s+parameters?|bop|choke|valve|rig|well\s*control)\b|\bshut[\s-]?in\b|\bcontrol\s+(the\s+)?rig\b/i

export const REFUSALS = {
  off_topic: {
    en: 'I can only help with using eRTMAC-NWIS — its screens, data, risk look-ahead, evidence, advisories, audit and sign-in. Please ask about the application.',
    hi: 'मैं केवल eRTMAC-NWIS के उपयोग में मदद कर सकता हूँ — इसकी स्क्रीन, डेटा, जोखिम पूर्वानुमान, प्रमाण, परामर्श, ऑडिट और साइन-इन। कृपया एप्लिकेशन के बारे में पूछें।',
    ta: 'நான் eRTMAC-NWIS பயன்பாட்டில் மட்டுமே உதவ முடியும் — அதன் திரைகள், தரவு, ஆபத்து முன்னறிவு, சான்று, ஆலோசனைகள், தணிக்கை மற்றும் உள்நுழைவு. பயன்பாடு பற்றிக் கேளுங்கள்.',
  },
  injection: {
    en: 'I can’t change how I work. I only answer questions about using eRTMAC-NWIS.',
    hi: 'मैं अपने काम करने का तरीका नहीं बदल सकता। मैं केवल eRTMAC-NWIS के उपयोग से जुड़े प्रश्नों के उत्तर देता हूँ।',
    ta: 'என் செயல்முறையை மாற்ற முடியாது. eRTMAC-NWIS பயன்பாடு குறித்த கேள்விகளுக்கு மட்டுமே பதிலளிப்பேன்.',
  },
  control: {
    en: 'NWIS is advisory decision support only: it never operates rig equipment or changes mud programs, drilling parameters or well-control settings. Those decisions belong to the drilling engineer. I can show you where NWIS presents the evidence (Risk Look-Ahead → “Why this alert?”).',
    hi: 'NWIS केवल परामर्श निर्णय सहायता है: यह कभी रिग उपकरण नहीं चलाता और मड प्रोग्राम, ड्रिलिंग पैरामीटर या वेल-कंट्रोल सेटिंग नहीं बदलता। ये निर्णय ड्रिलिंग इंजीनियर के हैं। मैं बता सकता हूँ कि NWIS प्रमाण कहाँ दिखाता है (जोखिम पूर्वानुमान → “यह अलर्ट क्यों?”)।',
    ta: 'NWIS ஆலோசனை முடிவு உதவி மட்டுமே: அது ஒருபோதும் ரிக் உபகரணங்களை இயக்காது, சேற்றுத் திட்டங்கள், துளையிடல் அளவுருக்கள் அல்லது கிணற்றுக் கட்டுப்பாட்டு அமைப்புகளை மாற்றாது. அந்த முடிவுகள் துளையிடல் பொறியாளருடையவை. NWIS சான்றை எங்கே காட்டுகிறது எனக் காட்ட முடியும் (ஆபத்து முன்னறிவு → “இந்த எச்சரிக்கை ஏன்?”).',
  },
}

// Help topics. Keywords are matched as substrings of the lower-cased question (all three languages).
export const TOPICS = [
  { id: 'greeting', keywords: ['hello', 'hey', 'thanks', 'thank you', 'नमस्ते', 'धन्यवाद', 'வணக்கம்', 'நன்றி', 'who are you', 'what can you do', 'help me'],
    answer: { en: 'Hello! I’m the NWIS assistant. Ask me how to use any screen — for example “How do I sign in?”, “What does the risk look-ahead show?” or “Why is OFF-04 empty?”.',
      hi: 'नमस्ते! मैं NWIS सहायक हूँ। किसी भी स्क्रीन के उपयोग के बारे में पूछें — जैसे “साइन इन कैसे करूँ?”, “जोखिम पूर्वानुमान क्या दिखाता है?” या “OFF-04 खाली क्यों है?”।',
      ta: 'வணக்கம்! நான் NWIS உதவியாளர். எந்தத் திரையையும் எப்படிப் பயன்படுத்துவது எனக் கேளுங்கள் — எ.கா. “எப்படி உள்நுழைவது?”, “ஆபத்து முன்னறிவு என்ன காட்டுகிறது?” அல்லது “OFF-04 ஏன் காலியாக உள்ளது?”.' } },
  { id: 'what', route: '/app/help', keywords: ['what is nwis', 'what is this', 'about nwis', 'ertmac', 'purpose', 'this app', 'this application', 'nwis क्या', 'यह एप', 'nwis என்ன', 'இந்த பயன்பாடு'],
    answer: { en: 'eRTMAC-NWIS (Nearby Wells Intelligence System) finds analogous nearby offset wells, aligns them by formation and depth, shows what happened at the same interval, and turns that history into a hazard look-ahead for the next 50/100/150 m with cited evidence. It is advisory only and runs on a synthetic demo dataset.',
      hi: 'eRTMAC-NWIS (निकटवर्ती कुआँ सूचना प्रणाली) समरूप निकटवर्ती ऑफ़सेट कुएँ ढूँढता है, उन्हें फ़ॉर्मेशन और गहराई से संरेखित करता है, उसी अंतराल पर क्या हुआ यह दिखाता है और उस इतिहास से अगले 50/100/150 मी. का खतरा पूर्वानुमान उद्धृत प्रमाण सहित बनाता है। यह केवल परामर्श है और कृत्रिम डेमो डेटा पर चलता है।',
      ta: 'eRTMAC-NWIS (அருகிலுள்ள கிணறுகள் தகவல் அமைப்பு) ஒப்புமையான அருகிலுள்ள ஆஃப்செட் கிணறுகளைக் கண்டறிந்து, பாறையடுக்கு மற்றும் ஆழத்தால் சீரமைத்து, அதே இடைவெளியில் என்ன நடந்தது எனக் காட்டி, அடுத்த 50/100/150 மீ.-க்கான ஆபத்து முன்னறிவை மேற்கோள் சான்றுடன் வழங்குகிறது. இது ஆலோசனை மட்டுமே; செயற்கை டெமோ தரவில் இயங்குகிறது.' } },
  { id: 'signin', route: '/login', keywords: ['sign in', 'signin', 'log in', 'login', 'demo account', 'evaluator', 'password', 'username', 'credentials', 'साइन इन', 'लॉगिन', 'पासवर्ड', 'डेमो खाता', 'உள்நுழை', 'கடவுச்சொல்', 'டெமோ கணக்கு'],
    answer: { en: 'On the Sign in page, click “Use demo account” (username evaluator) and then “Sign in”. The demo account is a reviewer on the synthetic dataset. Forgot your own password? Use “Forgot password?” on the same page.',
      hi: 'साइन इन पृष्ठ पर “डेमो खाता उपयोग करें” (उपयोगकर्ता नाम evaluator) दबाएँ, फिर “साइन इन” दबाएँ। डेमो खाता कृत्रिम डेटासेट पर समीक्षक है। अपना पासवर्ड भूल गए? उसी पृष्ठ पर “पासवर्ड भूल गए?” उपयोग करें।',
      ta: 'உள்நுழைவுப் பக்கத்தில் “டெமோ கணக்கைப் பயன்படுத்து” (பயனர்பெயர் evaluator) என்பதை அழுத்தி, பின் “உள்நுழை” அழுத்தவும். டெமோ கணக்கு செயற்கைத் தரவில் மதிப்பாய்வாளர். உங்கள் கடவுச்சொல் மறந்ததா? அதே பக்கத்தில் “கடவுச்சொல் மறந்ததா?” பயன்படுத்தவும்.' } },
  { id: 'signup', route: '/signup', keywords: ['sign up', 'signup', 'register', 'create account', 'new account', 'verification code', 'otp', 'reset password', 'खाता बनाएँ', 'पंजीकरण', 'सत्यापन कोड', 'கணக்கை உருவாக்கு', 'பதிவு செய்', 'சரிபார்ப்புக் குறியீடு'],
    answer: { en: 'Choose “Create an account”, fill in your name, email and a 12+ character password, then enter the 6-digit code sent to your email. New accounts start with the requester role; an administrator grants reviewer or admin.',
      hi: '“खाता बनाएँ” चुनें, नाम, ईमेल और 12+ अक्षरों का पासवर्ड भरें, फिर ईमेल पर आया 6 अंकों का कोड दर्ज करें। नए खाते अनुरोधकर्ता भूमिका से शुरू होते हैं; समीक्षक या प्रशासक भूमिका प्रशासक देता है।',
      ta: '“கணக்கை உருவாக்கு” என்பதைத் தேர்ந்தெடுத்து, பெயர், மின்னஞ்சல், 12+ எழுத்துக் கடவுச்சொல்லை நிரப்பி, மின்னஞ்சலில் வந்த 6 இலக்கக் குறியீட்டை உள்ளிடவும். புதிய கணக்குகள் கோரிக்கையாளர் பங்குடன் தொடங்கும்; மதிப்பாய்வாளர் அல்லது நிர்வாகி பங்கை நிர்வாகி வழங்குவார்.' } },
  { id: 'terms', keywords: ['terms', 'accept', 'advisory terms', 'शर्तें', 'स्वीकार', 'விதிமுறை', 'ஏற்று'],
    answer: { en: 'After first sign-in NWIS shows its advisory terms. Click “Accept and continue”; the acceptance is recorded on the audit log. They state that NWIS is advisory only and uses synthetic data.',
      hi: 'पहली बार साइन इन के बाद NWIS परामर्श शर्तें दिखाता है। “स्वीकार करें और आगे बढ़ें” दबाएँ; स्वीकृति ऑडिट लॉग में दर्ज होती है। इनमें लिखा है कि NWIS केवल परामर्श है और कृत्रिम डेटा उपयोग करता है।',
      ta: 'முதல் உள்நுழைவுக்குப் பின் NWIS தன் ஆலோசனை விதிமுறைகளைக் காட்டும். “ஏற்றுத் தொடரவும்” அழுத்தவும்; ஏற்பு தணிக்கைப் பதிவில் பதிவாகும். NWIS ஆலோசனை மட்டுமே, செயற்கைத் தரவைப் பயன்படுத்துகிறது என அவை கூறுகின்றன.' } },
  { id: 'dashboard', route: '/app/dashboard', keywords: ['dashboard', 'overview', 'home screen', 'डैशबोर्ड', 'अवलोकन', 'முகப்புப்பலகை', 'கண்ணோட்டம்'],
    answer: { en: 'The Dashboard shows the active well’s depth and formation, the hazard look-ahead cards, offset coverage within the chosen radius, a mini map, recent alerts and data quality. Use the radius (2–20 km) and look-ahead (50/100/150 m) buttons at the top.',
      hi: 'डैशबोर्ड सक्रिय कुएँ की गहराई और फ़ॉर्मेशन, खतरा पूर्वानुमान कार्ड, चुनी त्रिज्या में ऑफ़सेट कवरेज, लघु मानचित्र, हाल के अलर्ट और डेटा गुणवत्ता दिखाता है। ऊपर त्रिज्या (2–20 कि.मी.) और पूर्वानुमान दूरी (50/100/150 मी.) बटन उपयोग करें।',
      ta: 'முகப்புப்பலகை செயலில் உள்ள கிணற்றின் ஆழம், பாறையடுக்கு, ஆபத்து முன்னறிவு அட்டைகள், தேர்ந்த ஆரத்தில் ஆஃப்செட் கவரேஜ், சிறு வரைபடம், சமீபத்திய எச்சரிக்கைகள், தரவுத் தரம் ஆகியவற்றைக் காட்டுகிறது. மேலே உள்ள ஆரம் (2–20 கி.மீ.) மற்றும் முன்னோக்கு (50/100/150 மீ.) பொத்தான்களைப் பயன்படுத்தவும்.' } },
  { id: 'active', route: '/app/active', keywords: ['active well', 'active-01', 'off-0', 'off-1', 'offset well', 'empty', 'blank', 'no usable', 'insufficient', 'सक्रिय कुआँ', 'खाली', 'ऑफ़सेट कुआँ', 'செயலில் உள்ள கிணறு', 'காலி', 'ஆஃப்செட் கிணறு'],
    answer: { en: 'Only ACTIVE-01 is the well being drilled. OFF-01…OFF-11 are historical offset wells: they have no current bit depth, so MD/TVD/formation show “—” and the hazards say “Insufficient evidence / no usable analogs”. Select ACTIVE-01 in the “Active well” dropdown to see the full look-ahead.',
      hi: 'केवल ACTIVE-01 ही ड्रिल हो रहा कुआँ है। OFF-01…OFF-11 ऐतिहासिक ऑफ़सेट कुएँ हैं: इनकी वर्तमान बिट गहराई नहीं है, इसलिए MD/TVD/फ़ॉर्मेशन “—” दिखते हैं और खतरे “अपर्याप्त प्रमाण / कोई उपयोगी समरूप नहीं” बताते हैं। पूरा पूर्वानुमान देखने के लिए “सक्रिय कुआँ” सूची में ACTIVE-01 चुनें।',
      ta: 'ACTIVE-01 மட்டுமே தற்போது துளையிடப்படும் கிணறு. OFF-01…OFF-11 வரலாற்று ஆஃப்செட் கிணறுகள்: அவற்றுக்குத் தற்போதைய பிட் ஆழம் இல்லை, எனவே MD/TVD/பாறையடுக்கு “—” எனக் காட்டும்; ஆபத்துகள் “போதிய சான்று இல்லை” எனக் காட்டும். முழு முன்னறிவைக் காண “செயலில் உள்ள கிணறு” பட்டியலில் ACTIVE-01-ஐத் தேர்ந்தெடுக்கவும்.' } },
  { id: 'map', route: '/app/map', keywords: ['map', 'nearby wells', 'radius', 'distance', 'closest', 'मानचित्र', 'निकटवर्ती', 'त्रिज्या', 'வரைபடம்', 'அருகிலுள்ள', 'ஆரம்'],
    answer: { en: 'The Nearby Wells Map draws the backend’s radius query around the active well. Offsets are ranked by a transparent similarity score (formation, depth overlap, trajectory, program context, data quality), not by distance alone — the closest well can rank low if it lies across a fault. Click a well to see its scores.',
      hi: 'निकटवर्ती कुओं का मानचित्र सक्रिय कुएँ के चारों ओर बैकएंड की त्रिज्या खोज दिखाता है। ऑफ़सेट केवल दूरी से नहीं, पारदर्शी समानता स्कोर (फ़ॉर्मेशन, गहराई ओवरलैप, प्रक्षेप पथ, प्रोग्राम संदर्भ, डेटा गुणवत्ता) से क्रमित होते हैं — फ़ॉल्ट के पार का सबसे निकट कुआँ नीचे हो सकता है। स्कोर देखने के लिए कुएँ पर क्लिक करें।',
      ta: 'அருகிலுள்ள கிணறுகள் வரைபடம் செயலில் உள்ள கிணற்றைச் சுற்றிய பின்தள ஆரத் தேடலைக் காட்டுகிறது. ஆஃப்செட்கள் தூரத்தால் மட்டுமல்ல, வெளிப்படையான ஒற்றுமை மதிப்பெண்ணால் (பாறையடுக்கு, ஆழ மேற்பொருந்தல், பாதை, திட்டச் சூழல், தரவுத் தரம்) தரவரிசைப்படுத்தப்படுகின்றன — பிளவின் குறுக்கே உள்ள அருகிலுள்ள கிணறு கீழே இருக்கலாம். மதிப்பெண்களைக் காண கிணற்றைக் கிளிக் செய்யவும்.' } },
  { id: 'offset', route: '/app/offset-analysis', keywords: ['offset analysis', 'similarity', 'ranking', 'rank', 'score', 'compare', 'pin', 'exclude', 'analog', 'समानता', 'क्रम', 'स्कोर', 'तुलना', 'ஒற்றுமை', 'தரவரிசை', 'மதிப்பெண்', 'ஒப்பிடு'],
    answer: { en: 'Offset Analysis lists the ranked offsets with every component score so the ranking can be challenged. Pin, compare or exclude wells for your own view — this never changes the backend ranking or the risk engine. Ranking is deterministic, never produced by an AI model.',
      hi: 'ऑफ़सेट विश्लेषण हर घटक स्कोर के साथ क्रमित ऑफ़सेट दिखाता है ताकि क्रम को परखा जा सके। अपने दृश्य के लिए कुएँ पिन, तुलना या बाहर करें — इससे बैकएंड क्रम या जोखिम इंजन नहीं बदलता। क्रम निर्धारित नियमों से बनता है, AI मॉडल से नहीं।',
      ta: 'ஆஃப்செட் பகுப்பாய்வு ஒவ்வொரு கூறு மதிப்பெண்ணுடன் தரவரிசை ஆஃப்செட்களைக் காட்டுகிறது. உங்கள் காட்சிக்காகக் கிணறுகளைப் பின், ஒப்பீடு அல்லது விலக்கு செய்யலாம் — இது பின்தளத் தரவரிசையையோ ஆபத்து இயந்திரத்தையோ மாற்றாது. தரவரிசை நிர்ணயமான விதிகளால், AI மாதிரியால் அல்ல.' } },
  { id: 'correlation', route: '/app/correlation', keywords: ['correlation', 'formation', 'tvd', 'stratigraphy', 'tipam', 'casing', 'फ़ॉर्मेशन', 'सहसंबंध', 'பாறையடுக்கு', 'ஒப்பீடு'],
    answer: { en: 'Formation Correlation aligns the active well and selected offsets on one TVD axis with formation intervals, drilling events, casing points and the look-ahead window. Measured depth (MD) misleads for deviated wells, so NWIS aligns by TVD and formation tops; interpreted intervals are hatched.',
      hi: 'फ़ॉर्मेशन सहसंबंध सक्रिय कुएँ और चुने ऑफ़सेट को एक TVD अक्ष पर फ़ॉर्मेशन अंतराल, ड्रिलिंग घटनाओं, केसिंग बिंदुओं और पूर्वानुमान खिड़की के साथ संरेखित करता है। झुके कुओं में MD भ्रमित करता है, इसलिए NWIS TVD और फ़ॉर्मेशन शीर्ष से संरेखित करता है; व्याख्यायित अंतराल धारीदार होते हैं।',
      ta: 'பாறையடுக்கு ஒப்பீடு செயலில் உள்ள கிணற்றையும் தேர்ந்த ஆஃப்செட்களையும் ஒரே TVD அச்சில் பாறையடுக்கு இடைவெளிகள், துளையிடல் நிகழ்வுகள், கேசிங் புள்ளிகள், முன்னோக்குச் சாளரத்துடன் சீரமைக்கிறது. சாய்ந்த கிணறுகளில் MD தவறாக வழிநடத்தும்; எனவே NWIS TVD மற்றும் பாறையடுக்கு மேல்மட்டங்களால் சீரமைக்கிறது.' } },
  { id: 'events', route: '/app/events', keywords: ['drilling events', 'events', 'report', 'ddr', 'wcr', 'source wording', 'stuck pipe', 'mud loss', 'घटना', 'रिपोर्ट', 'निकाली', 'நிகழ்வு', 'அறிக்கை'],
    answer: { en: 'Drilling Events lists historical events extracted from daily drilling (DDR) and well completion (WCR) reports. Each card keeps the original source wording next to the normalized fields, with report, page, depth, formation, mitigation and outcome. Filter by well, formation, type and depth.',
      hi: 'ड्रिलिंग घटनाएँ दैनिक ड्रिलिंग (DDR) और कुआँ पूर्णता (WCR) रिपोर्टों से निकाली ऐतिहासिक घटनाएँ दिखाती हैं। हर कार्ड सामान्यीकृत फ़ील्ड के साथ मूल स्रोत शब्द, रिपोर्ट, पृष्ठ, गहराई, फ़ॉर्मेशन, निवारण और परिणाम रखता है। कुआँ, फ़ॉर्मेशन, प्रकार और गहराई से फ़िल्टर करें।',
      ta: 'துளையிடல் நிகழ்வுகள் தினசரி துளையிடல் (DDR) மற்றும் கிணறு நிறைவு (WCR) அறிக்கைகளிலிருந்து பிரித்த வரலாற்று நிகழ்வுகளைக் காட்டுகிறது. ஒவ்வொரு அட்டையும் மூலச் சொற்கள், அறிக்கை, பக்கம், ஆழம், பாறையடுக்கு, தணிப்பு, விளைவு ஆகியவற்றைக் கொண்டுள்ளது. கிணறு, பாறையடுக்கு, வகை, ஆழம் மூலம் வடிகட்டலாம்.' } },
  { id: 'risk', route: '/app/risk', keywords: ['risk', 'look-ahead', 'lookahead', 'hazard', 'probability', 'confidence', '50 m', '100 m', '150 m', 'uncalibrated', 'जोखिम', 'पूर्वानुमान', 'खतरा', 'संभावना', 'ஆபத்து', 'முன்னறிவு', 'நிகழ்தகவு'],
    answer: { en: 'Risk Look-Ahead gives each hazard (stuck pipe, mud loss, kick/overpressure, torque/drag) its own probability, confidence, trend and evidence for the next 50, 100 or 150 m. Values are uncalibrated prototype estimates from matched offset history plus a bounded telemetry modifier — there is no single overall AI risk.',
      hi: 'जोखिम पूर्वानुमान हर खतरे (फँसा पाइप, मड लॉस, किक/अतिदाब, टॉर्क/ड्रैग) को अगले 50, 100 या 150 मी. के लिए अलग संभावना, विश्वास, रुझान और प्रमाण देता है। मान मिलान वाले ऑफ़सेट इतिहास और सीमित टेलीमेट्री से बने अकैलिब्रेटेड प्रोटोटाइप अनुमान हैं — कोई एक समग्र AI जोखिम नहीं है।',
      ta: 'ஆபத்து முன்னறிவு ஒவ்வொரு ஆபத்துக்கும் (சிக்கிய குழாய், சேற்று இழப்பு, கிக்/அதிக அழுத்தம், முறுக்கு/இழுவை) அடுத்த 50, 100 அல்லது 150 மீ.-க்குத் தனி நிகழ்தகவு, நம்பகத்தன்மை, போக்கு, சான்று வழங்குகிறது. மதிப்புகள் பொருந்திய ஆஃப்செட் வரலாறு மற்றும் வரம்புள்ள டெலிமெட்ரியிலிருந்து பெற்ற அளவுத்திருத்தமற்ற மதிப்பீடுகள் — ஒற்றை ஒட்டுமொத்த AI ஆபத்து இல்லை.' } },
  { id: 'why', route: '/app/risk', keywords: ['why this alert', 'why alert', 'evidence', 'explain', 'cited', 'source', 'pdf', 'प्रमाण', 'क्यों', 'उद्धृत', 'சான்று', 'ஏன்', 'மேற்கோள்'],
    answer: { en: 'On any risk card click “Why this alert?”. The drawer shows the supporting offset wells and their similarity, historical event depths, the cited report passages (open the source PDF at the exact page), telemetry features, missing evidence and why the confidence is what it is.',
      hi: 'किसी भी जोखिम कार्ड पर “यह अलर्ट क्यों?” दबाएँ। इसमें समर्थक ऑफ़सेट कुएँ और उनकी समानता, ऐतिहासिक घटना गहराइयाँ, उद्धृत रिपोर्ट अंश (स्रोत PDF सही पृष्ठ पर खुलता है), टेलीमेट्री विशेषताएँ, अनुपलब्ध प्रमाण और विश्वास स्तर का कारण दिखते हैं।',
      ta: 'எந்த ஆபத்து அட்டையிலும் “இந்த எச்சரிக்கை ஏன்?” அழுத்தவும். அதில் ஆதரவு ஆஃப்செட் கிணறுகள், அவற்றின் ஒற்றுமை, வரலாற்று நிகழ்வு ஆழங்கள், மேற்கோள் அறிக்கைப் பகுதிகள் (மூல PDF சரியான பக்கத்தில் திறக்கும்), டெலிமெட்ரி அம்சங்கள், விடுபட்ட சான்று, நம்பகத்தன்மைக்கான காரணம் காட்டப்படும்.' } },
  { id: 'live', route: '/app/live', keywords: ['live drilling', 'telemetry', 'replay', 'torque', 'rop', 'witsml', 'real time', 'realtime', 'टेलीमेट्री', 'लाइव', 'रीप्ले', 'டெலிமெட்ரி', 'நேரடி', 'மறுஒளிபரப்பு'],
    answer: { en: 'Live Drilling shows depth- and time-synchronised drilling parameters for the active well. In this demo it is clearly labelled SIMULATED / REPLAY data — never an Oil India or eRTMAC live feed. A WITSML / ETP-ready adapter is planned.',
      hi: 'लाइव ड्रिलिंग सक्रिय कुएँ के गहराई और समय से समन्वित ड्रिलिंग पैरामीटर दिखाता है। इस डेमो में यह स्पष्ट रूप से सिम्युलेटेड / रीप्ले डेटा लिखा है — कभी Oil India या eRTMAC का लाइव फ़ीड नहीं। WITSML / ETP-तैयार एडॉप्टर नियोजित है।',
      ta: 'நேரடி துளையிடல் செயலில் உள்ள கிணற்றின் ஆழம் மற்றும் நேரத்துடன் ஒத்திசைந்த அளவுருக்களைக் காட்டுகிறது. இந்த டெமோவில் அது தெளிவாக உருவகப்படுத்திய / மறுஒளிபரப்புத் தரவு எனக் குறிக்கப்பட்டுள்ளது — Oil India அல்லது eRTMAC நேரடி ஊட்டம் அல்ல. WITSML / ETP-தயார் இணைப்பி திட்டமிடப்பட்டுள்ளது.' } },
  { id: 'knowledge', route: '/app/knowledge', keywords: ['knowledge search', 'search', 'ask a question', 'ai summary', 'qwen', 'question', 'ज्ञान खोज', 'खोज', 'सारांश', 'அறிவுத் தேடல்', 'தேடல்', 'சுருக்கம்'],
    answer: { en: 'Knowledge Search answers natural-language questions from cited historical evidence only (hybrid search with a reranker). Every result carries its well, report, page, depth and formation. Optionally, “Generate AI summary in your browser” runs Qwen 3.5 on your own GPU; the cited answer never depends on it.',
      hi: 'ज्ञान खोज सामान्य भाषा के प्रश्नों का उत्तर केवल उद्धृत ऐतिहासिक प्रमाण से देती है (रीरैंकर सहित हाइब्रिड खोज)। हर परिणाम में कुआँ, रिपोर्ट, पृष्ठ, गहराई और फ़ॉर्मेशन होता है। वैकल्पिक रूप से “अपने ब्राउज़र में AI सारांश बनाएँ” आपके GPU पर Qwen 3.5 चलाता है; उद्धृत उत्तर उस पर निर्भर नहीं।',
      ta: 'அறிவுத் தேடல் இயல்பு மொழிக் கேள்விகளுக்கு மேற்கோள் வரலாற்றுச் சான்றிலிருந்து மட்டுமே பதிலளிக்கிறது (மறுதரவரிசையுடன் கலப்புத் தேடல்). ஒவ்வொரு முடிவிலும் கிணறு, அறிக்கை, பக்கம், ஆழம், பாறையடுக்கு உள்ளன. விருப்பமாக “உங்கள் உலாவியில் AI சுருக்கம் உருவாக்கு” உங்கள் GPU-இல் Qwen 3.5-ஐ இயக்கும்; மேற்கோள் பதில் அதைச் சார்ந்ததல்ல.' } },
  { id: 'advisories', route: '/app/advisories', keywords: ['advisory', 'advisories', 'alert', 'acknowledge', 'review', 'dismiss', 'परामर्श', 'अलर्ट', 'समीक्षा', 'ஆலோசனை', 'எச்சரிக்கை', 'மதிப்பாய்வு'],
    answer: { en: 'Advisories are raised when successive assessments show a sustained risk. A reviewer can acknowledge, mark reviewed or dismiss for insufficient evidence, with a reason of at least 5 characters. Every decision is written to the audit log; nothing changes rig equipment.',
      hi: 'लगातार आकलनों में स्थायी जोखिम दिखने पर परामर्श बनते हैं। समीक्षक कम से कम 5 अक्षरों के कारण के साथ स्वीकार, समीक्षित या अपर्याप्त प्रमाण पर खारिज कर सकता है। हर निर्णय ऑडिट लॉग में दर्ज होता है; कुछ भी रिग उपकरण नहीं बदलता।',
      ta: 'தொடர்ச்சியான மதிப்பீடுகள் நீடித்த ஆபத்தைக் காட்டும்போது ஆலோசனைகள் எழுப்பப்படும். மதிப்பாய்வாளர் குறைந்தது 5 எழுத்துக் காரணத்துடன் ஏற்கலாம், மதிப்பாய்வு செய்ததாகக் குறிக்கலாம் அல்லது போதிய சான்று இல்லையென நிராகரிக்கலாம். ஒவ்வொரு முடிவும் தணிக்கைப் பதிவில் எழுதப்படும்; எதுவும் ரிக் உபகரணங்களை மாற்றாது.' } },
  { id: 'audit', route: '/app/audit', keywords: ['audit', 'audit log', 'chain', 'hash', 'tamper', 'ऑडिट', 'தணிக்கை'],
    answer: { en: 'Audit shows the hash-chained log of terms acceptance, risk assessments, knowledge queries and advisory reviews. “Chain verification” recomputes the chain to prove nothing was altered — tamper-evident, not tamper-proof. Reviewers and admins can open it.',
      hi: 'ऑडिट शर्तों की स्वीकृति, जोखिम आकलन, ज्ञान खोज और परामर्श समीक्षाओं का हैश-शृंखलित लॉग दिखाता है। “शृंखला सत्यापन” शृंखला दोबारा गणना करके दिखाता है कि कुछ बदला नहीं गया — छेड़छाड़ दिखती है, पर पूरी तरह रोकी नहीं जा सकती। समीक्षक और प्रशासक इसे खोल सकते हैं।',
      ta: 'தணிக்கை விதிமுறை ஏற்பு, ஆபத்து மதிப்பீடுகள், அறிவுத் தேடல்கள், ஆலோசனை மதிப்பாய்வுகளின் ஹாஷ்-சங்கிலிப் பதிவைக் காட்டுகிறது. “சங்கிலிச் சரிபார்ப்பு” சங்கிலியை மீண்டும் கணக்கிட்டு எதுவும் மாற்றப்படவில்லை என நிரூபிக்கிறது. மதிப்பாய்வாளர்களும் நிர்வாகிகளும் இதைத் திறக்கலாம்.' } },
  { id: 'data', route: '/app/help', keywords: ['synthetic', 'real data', 'oil india data', 'dataset', 'demo data', 'fake', 'कृत्रिम', 'डेटा', 'செயற்கை', 'தரவு'],
    answer: { en: 'All data here is a clearly labelled synthetic demo dataset (dataset_origin = synthetic_demo). It proves the data model and workflows; it is not Oil India data. Telemetry is simulated replay unless a screen explicitly says LIVE.',
      hi: 'यहाँ का सारा डेटा स्पष्ट रूप से चिह्नित कृत्रिम डेमो डेटासेट है (dataset_origin = synthetic_demo)। यह डेटा मॉडल और कार्यप्रवाह सिद्ध करता है; यह Oil India का डेटा नहीं है। जब तक स्क्रीन पर LIVE न लिखा हो, टेलीमेट्री सिम्युलेटेड रीप्ले है।',
      ta: 'இங்குள்ள எல்லாத் தரவும் தெளிவாகக் குறிக்கப்பட்ட செயற்கை டெமோ தரவுத்தொகுப்பு (dataset_origin = synthetic_demo). இது தரவு மாதிரியையும் பணிமுறைகளையும் நிரூபிக்கிறது; இது Oil India தரவு அல்ல. திரையில் LIVE எனக் குறிப்பிடாவிட்டால் டெலிமெட்ரி உருவகப்படுத்திய மறுஒளிபரப்பு.' } },
  { id: 'safety', keywords: ['safe', 'safety', 'control', 'operate', 'automatic', 'rig equipment', 'सुरक्षा', 'नियंत्रण', 'பாதுகாப்பு', 'கட்டுப்பாடு'],
    answer: REFUSALS.control },
  { id: 'language', keywords: ['language', 'hindi', 'tamil', 'english', 'translate', 'भाषा', 'हिन्दी', 'तमिल', 'மொழி', 'தமிழ்', 'இந்தி'],
    answer: { en: 'Use the “Language” selector at the top right to switch the whole application between English, हिन्दी and தமிழ். I answer in the language you choose or write in. Well IDs, numbers and quoted report evidence stay exactly as recorded.',
      hi: 'पूरे एप्लिकेशन को English, हिन्दी और தமிழ் के बीच बदलने के लिए ऊपर दाईं ओर “भाषा” चयनकर्ता उपयोग करें। मैं आपकी चुनी या लिखी भाषा में उत्तर देता हूँ। कुएँ की ID, संख्याएँ और उद्धृत रिपोर्ट प्रमाण जैसे दर्ज हैं वैसे ही रहते हैं।',
      ta: 'முழுப் பயன்பாட்டையும் English, हिन्दी, தமிழ் இடையே மாற்ற மேல் வலதுபுறம் உள்ள “மொழி” தேர்வியைப் பயன்படுத்தவும். நீங்கள் தேர்ந்த அல்லது எழுதும் மொழியில் பதிலளிப்பேன். கிணறு ID-கள், எண்கள், மேற்கோள் அறிக்கைச் சான்று பதிவானபடியே இருக்கும்.' } },
  { id: 'voice', keywords: ['voice', 'speak', 'microphone', 'mic', 'read aloud', 'आवाज़', 'बोल', 'माइक', 'குரல்', 'பேசு', 'மைக்'],
    answer: { en: 'Press the microphone button in this assistant and speak your question in English, Hindi or Tamil; press the speaker button to hear an answer. Voice uses your browser’s speech features, so it works best in Chrome or Edge.',
      hi: 'इस सहायक में माइक्रोफ़ोन बटन दबाकर अपना प्रश्न अंग्रेज़ी, हिन्दी या तमिल में बोलें; उत्तर सुनने के लिए स्पीकर बटन दबाएँ। आवाज़ आपके ब्राउज़र की स्पीच सुविधा उपयोग करती है, इसलिए Chrome या Edge में सबसे अच्छी चलती है।',
      ta: 'இந்த உதவியாளரில் மைக்ரோஃபோன் பொத்தானை அழுத்தி உங்கள் கேள்வியை ஆங்கிலம், இந்தி அல்லது தமிழில் பேசுங்கள்; பதிலைக் கேட்க ஸ்பீக்கர் பொத்தானை அழுத்தவும். குரல் உங்கள் உலாவியின் பேச்சு வசதியைப் பயன்படுத்துகிறது; Chrome அல்லது Edge-இல் சிறப்பாக இயங்கும்.' } },
  { id: 'help', route: '/app/help', keywords: ['help', 'demo flow', 'glossary', 'how to use', 'guide', 'tutorial', 'सहायता', 'कैसे उपयोग', 'உதவி', 'எப்படிப் பயன்படுத்துவது'],
    answer: { en: 'Open “Help & Resources” in the left menu for the 3-minute judge demo flow, the glossary, the data disclosure and a live API status check. Suggested flow: Dashboard → Nearby Wells Map → Risk Look-Ahead → “Why this alert?” → Knowledge Search → Advisories → Audit.',
      hi: 'बाएँ मेनू में “सहायता और संसाधन” खोलें: 3 मिनट का निर्णायक डेमो क्रम, शब्दावली, डेटा प्रकटीकरण और लाइव API स्थिति। सुझाया क्रम: डैशबोर्ड → निकटवर्ती कुओं का मानचित्र → जोखिम पूर्वानुमान → “यह अलर्ट क्यों?” → ज्ञान खोज → परामर्श → ऑडिट।',
      ta: 'இடது பட்டியலில் “உதவி மற்றும் வளங்கள்” திறக்கவும்: 3 நிமிட நடுவர் டெமோ வரிசை, சொற்களஞ்சியம், தரவு வெளிப்படுத்தல், நேரடி API நிலை. பரிந்துரை வரிசை: முகப்புப்பலகை → அருகிலுள்ள கிணறுகள் வரைபடம் → ஆபத்து முன்னறிவு → “இந்த எச்சரிக்கை ஏன்?” → அறிவுத் தேடல் → ஆலோசனைகள் → தணிக்கை.' } },
]

const normalize = text => ` ${String(text).toLowerCase().replace(/[^\p{L}\p{M}\p{N}\s-]/gu, ' ').replace(/\s+/g, ' ')} `

export function rankTopics(question) {
  const text = normalize(question)
  return TOPICS.map(topic => ({ topic, score: topic.keywords.reduce((sum, keyword) => sum + (text.includes(normalize(keyword).trim()) ? keyword.length : 0), 0) }))
    .filter(hit => hit.score > 0).sort((a, b) => b.score - a.score)
}

// Deterministic first pass. Returns { kind, lang, text, topics, route }; kind 'answer' may be enriched by the model.
export function respond(question, uiLanguage = 'en') {
  const q = String(question || '').trim().slice(0, 500)
  const lang = detectLanguage(q, uiLanguage)
  if (!q) return { kind: 'empty', lang, text: '' }
  if (INJECTION.test(q)) return { kind: 'injection', lang, text: REFUSALS.injection[lang] }
  if (CONTROL.test(q)) return { kind: 'control', lang, text: REFUSALS.control[lang] }
  const hits = rankTopics(q)
  if (!hits.length) return { kind: 'off_topic', lang, text: REFUSALS.off_topic[lang] }
  const best = hits[0].topic
  return { kind: 'answer', lang, text: best.answer[lang], route: best.route, topics: hits.slice(0, 3).map(hit => hit.topic) }
}

// Grounded prompt for the optional in-browser model: only the matched help notes, reply language fixed.
export function assistantMessages(question, reply) {
  const notes = reply.topics.map((topic, i) => `[${i + 1}] ${topic.answer.en}`).join('\n')
  return [
    { role: 'system', content: 'You are the in-app help assistant of eRTMAC-NWIS. Answer ONLY using the help notes below, about using this application. '
      + 'If the notes do not answer the question, say you can only help with using eRTMAC-NWIS. Never give drilling or rig-control instructions; NWIS is advisory only. '
      + `Reply in ${LANGS[reply.lang]} only, in under 90 words. Keep well IDs such as ACTIVE-01 unchanged.\n\nHelp notes:\n${notes}` },
    { role: 'user', content: question },
  ]
}
