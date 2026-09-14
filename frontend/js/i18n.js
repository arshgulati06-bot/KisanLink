/**
 * KisanLink — i18n / Multilingual Support Module
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Frontend Step 5: Full 13-Language Multilingual Architecture
 *
 * Supported 13 Indian Languages:
 *   - en: English
 *   - hi: हिन्दी (Hindi)
 *   - mr: मराठी (Marathi)
 *   - gu: ગુજરાતી (Gujarati)
 *   - pa: ਪੰਜਾਬੀ (Punjabi)
 *   - bn: বাংলা (Bengali)
 *   - ta: தமிழ் (Tamil)
 *   - te: తెలుగు (Telugu)
 *   - kn: ಕನ್ನಡ (Kannada)
 *   - ml: മലയാളം (Malayalam)
 *   - or: ଓଡ଼ିଆ (Odia)
 *   - as: অসমীয়া (Assamese)
 *   - ur: اردو (Urdu)
 *
 * ARCHITECTURE:
 *   - Centralized dictionary with stable translation keys.
 *   - Fallback hierarchy: selected locale -> English -> key.
 *   - Persistent selection via localStorage ('kl_locale').
 *   - Broadcasts 'kl:localeChanged' custom event for reactive UI updates.
 */

var KL_I18n = (function () {

  var LOCALES = {
    en: { name: 'English', native: 'English', bcp47: 'en-IN' },
    hi: { name: 'Hindi', native: 'हिन्दी', bcp47: 'hi-IN' },
    mr: { name: 'Marathi', native: 'मराठी', bcp47: 'mr-IN' },
    gu: { name: 'Gujarati', native: 'ગુજરાતી', bcp47: 'gu-IN' },
    pa: { name: 'Punjabi', native: 'ਪੰਜਾਬੀ', bcp47: 'pa-IN' },
    bn: { name: 'Bengali', native: 'বাংলা', bcp47: 'bn-IN' },
    ta: { name: 'Tamil', native: 'தமிழ்', bcp47: 'ta-IN' },
    te: { name: 'Telugu', native: 'తెలుగు', bcp47: 'te-IN' },
    kn: { name: 'Kannada', native: 'ಕನ್ನಡ', bcp47: 'kn-IN' },
    ml: { name: 'Malayalam', native: 'മലയാളം', bcp47: 'ml-IN' },
    or: { name: 'Odia', native: 'ଓଡ଼ିଆ', bcp47: 'or-IN' },
    as: { name: 'Assamese', native: 'অসমীয়া', bcp47: 'as-IN' },
    ur: { name: 'Urdu', native: 'اردو', bcp47: 'ur-IN' }
  };

  var SUPPORTED = Object.keys(LOCALES);
  var DEFAULT   = 'en';
  var _locale   = DEFAULT;

  /* ── Translation Dictionary ────────────────────────────────────────────── */
  var TRANSLATIONS = {
    en: {
      /* Nav & Topbar */
      'nav.overview':        'Overview',
      'nav.saleLots':        'My Sale Lots',
      'nav.marketIntel':     'Market Intelligence',
      'nav.recommendation':  'Recommendation',
      'nav.buyerMatches':    'Buyer Matches',
      'nav.offers':          'Received Offers',
      'nav.transactions':    'Transactions',
      'nav.cropQuality':     'Crop Quality Check',
      'nav.priceOutlook':    'Price Outlook',
      'nav.bestAction':      'Best Action',
      'topbar.createLot':    '+ Create Sale Lot',
      'topbar.switchBuyer':  'Switch to Buyer Portal',
      'topbar.home':         'Home',

      /* Quick Actions */
      'qa.title':            'Quick Farmer Actions',
      'qa.sellNow':          'SELL NOW',
      'qa.wait':             'WAIT FOR BETTER PRICE',
      'qa.compare':          'COMPARE MARKETS',
      'qa.checkQuality':     'CHECK CROP QUALITY',
      'qa.findBuyers':       'FIND VERIFIED BUYERS',

      /* Section Headings */
      'section.bestAction':    'Best Action for Your Crop',
      'section.priceOutlook':  'Price Outlook & 7-Day Forecast',
      'section.marketCompare': 'Compare Nearby Markets',
      'section.buyerMatches':  'Buyer Opportunities',
      'section.notifications': 'Activity & Notifications',
      'section.cropQuality':   'Crop Quality Check',
      'section.saleLots':      'My Active Sale Lots',

      /* Actions & Buttons */
      'action.sellNow':        'SELL NOW',
      'action.wait':           'WAIT',
      'action.compare':        'COMPARE MARKET',
      'action.analyze':        'Analyze Quality',
      'action.viewDetail':     'View Details',
      'action.makeOffer':      'Make / Review Offer',
      'action.takePhoto':      'Take Photo',
      'action.uploadImage':    'Upload Image',
      'action.capture':        'Capture Photo',
      'action.retake':         'Retake',
      'action.remove':         'Remove',
      'action.browse':         'Browse File',
      'action.analyzeAgain':   'Analyze Again',
      'action.applyPipeline':  'Apply Quality to Decision Engine',
      'action.getForecast':    'Get Forecast',
      'action.fetchMarkets':   'Compare Markets',

      /* Crop Quality Guidelines */
      'cqa.guide.title':       'Photo Quality Guidance for Best Results',
      'cqa.guide.g1':          'Take the photo in good natural light (avoid dark shadows).',
      'cqa.guide.g2':          'Keep the crop clearly visible and centered in the frame.',
      'cqa.guide.g3':          'Avoid blurry or out-of-focus camera angles.',
      'cqa.guide.g4':          'Show crop skin surface, size, and color clearly.',

      /* Crop Quality States */
      'cqa.state.notAssessed': 'Quality Result Will Appear Here',
      'cqa.state.notAssessedSub': 'Select a photo mode, provide a crop image, and click "Analyze Quality" to begin.',
      'cqa.state.assessing':   'Analysing Crop Quality...',
      'cqa.state.assessingSub':'Sending image for quality assessment. This may take a few moments.',
      'cqa.state.gradeLabel':  'Indicative Grade',
      'cqa.state.confLabel':   'Model Confidence',
      'cqa.state.indicators':  'Visible Quality Indicators',
      'cqa.state.placeholder': 'Awaiting ML Connection',
      'cqa.state.placeholderMsg': 'Quality assessment will appear when the ML service is connected.',
      'cqa.state.gradePending':'Grade will appear after quality assessment.',

      /* Status & Badges */
      'status.demo':           'Demo Dataset',
      'status.placeholder':    'ML Placeholder',
      'status.apiPending':     'API Pending',
      'status.open':           'OPEN',

      /* Chat & Voice Assistant */
      'chat.title':            'KisanLink Assistant',
      'chat.apiNotice':        'Assistant backend not connected. Responses are placeholder only.',
      'chat.empty':            'Ask about your crop, market prices, or buyer opportunities.',
      'chat.placeholder':      'Ask anything about your crop or market...',
      'chat.send':             'Send',
      'chat.voiceStart':       'Voice input (Speak)',
      'chat.voiceListening':   'Listening... Speak now',
      'chat.voiceStop':        'Stop Listening',
      'chat.voiceUnsupported': 'Voice input is not supported in this browser. You can use text instead.',
      'chat.speakReply':       'Listen to response',
      'chat.q1':               'Where should I sell?',
      'chat.q2':               'What is the current market price?',
      'chat.q3':               'Should I sell now or wait?',
      'chat.q4':               'Show my buyer opportunities',

      /* Decision Engine / Best Action */
      'ba.crop':               'Crop',
      'ba.quality':            'Quality Grade',
      'ba.location':           'Location',
      'ba.quantity':           'Quantity',
      'ba.marketPrice':        'Current Market Price',
      'ba.forecast':           '7-Day Forecast',
      'ba.demand':             'Buyer Demand',
      'ba.logistics':          'Est. Logistics Cost',
      'ba.netRealisation':     'Expected Net Realisation',
      'ba.netNote':            'After estimated logistics and market deductions.',
      'ba.recLabel':           'Recommended Action',

      /* Profile */
      'profile.title':         'Farmer Profile',
      'profile.contact':       'Contact',
      'profile.language':      'Language',
      'profile.switch':        'Switch Account'
    },

    hi: {
      'nav.overview':        'अवलोकन',
      'nav.saleLots':        'मेरे बिक्री लॉट',
      'nav.marketIntel':     'बाज़ार इंटेलिजेंस',
      'nav.recommendation':  'सिफारिश',
      'nav.buyerMatches':    'खरीदार मिलान',
      'nav.offers':          'प्राप्त ऑफ़र',
      'nav.transactions':    'लेनदेन',
      'nav.cropQuality':     'फसल गुणवत्ता जांच',
      'nav.priceOutlook':    'मूल्य दृष्टिकोण',
      'nav.bestAction':      'सर्वोत्तम कार्यवाही',
      'topbar.createLot':    '+ बिक्री लॉट बनाएं',
      'topbar.switchBuyer':  'खरीदार पोर्टल पर जाएं',
      'topbar.home':         'होम',

      'qa.title':            'किसान त्वरित कार्य',
      'qa.sellNow':          'अभी बेचें',
      'qa.wait':             'बेहतर मूल्य के लिए रुकें',
      'qa.compare':          'मंडी भाव तुलना करें',
      'qa.checkQuality':     'फसल गुणवत्ता जांचें',
      'qa.findBuyers':       'सत्यापित खरीदार खोजें',

      'section.bestAction':    'आपकी फसल के लिए सर्वोत्तम कार्यवाही',
      'section.priceOutlook':  'मूल्य दृष्टिकोण और 7-दिन का पूर्वानुमान',
      'section.marketCompare': 'नज़दीकी बाज़ारों की तुलना करें',
      'section.buyerMatches':  'खरीदार अवसर',
      'section.notifications': 'गतिविधि और सूचनाएं',
      'section.cropQuality':   'फसल गुणवत्ता जांच',
      'section.saleLots':      'सक्रिय बिक्री लॉट',

      'action.sellNow':        'अभी बेचें',
      'action.wait':           'प्रतीक्षा करें',
      'action.compare':        'बाज़ार की तुलना करें',
      'action.analyze':        'गुणवत्ता विश्लेषण',
      'action.viewDetail':     'विवरण देखें',
      'action.makeOffer':      'ऑफ़र करें / समीक्षा करें',
      'action.takePhoto':      'फोटो खींचें',
      'action.uploadImage':    'तस्वीर अपलोड करें',
      'action.capture':        'फोटो लें',
      'action.retake':         'दोबारा लें',
      'action.remove':         'हटाएं',
      'action.browse':         'फ़ाइल चुनें',
      'action.analyzeAgain':   'पुनः विश्लेषण करें',
      'action.applyPipeline':  'गुणवत्ता निर्णय इंजन में लागू करें',
      'action.getForecast':    'पूर्वानुमान प्राप्त करें',
      'action.fetchMarkets':   'बाज़ारों की तुलना करें',

      'cqa.guide.title':       'सटीक जांच हेतु फोटो सुझाव',
      'cqa.guide.g1':          'फोटो अच्छी प्राकृतिक रोशनी में लें (छाया से बचें)।',
      'cqa.guide.g2':          'फसल को कैमरे के बीच में स्पष्ट रखें।',
      'cqa.guide.g3':          'धुंधली या अंधेरी फोटो से बचें।',
      'cqa.guide.g4':          'फसल का रंग, आकार और छिलका साफ दिखना चाहिए।',

      'cqa.state.notAssessed': 'गुणवत्ता परिणाम यहाँ दिखाई देगा',
      'cqa.state.notAssessedSub': 'फोटो चुनें या खींचें, और "गुणवत्ता विश्लेषण" पर क्लिक करें।',
      'cqa.state.assessing':   'फसल गुणवत्ता का विश्लेषण हो रहा है...',
      'cqa.state.assessingSub':'छवि विश्लेषण के लिए भेजी जा रही है। कृपया प्रतीक्षा करें।',
      'cqa.state.gradeLabel':  'अनुमानित ग्रेड',
      'cqa.state.confLabel':   'मॉडल विश्वसनीयता',
      'cqa.state.indicators':  'दिखने वाले गुणवत्ता संकेतक',
      'cqa.state.placeholder': 'ML सेवा से जुड़ने की प्रतीक्षा',
      'cqa.state.placeholderMsg': 'ML सेवा कनेक्ट होने पर गुणवत्ता मूल्यांकन उपलब्ध होगा।',
      'cqa.state.gradePending':'गुणवत्ता मूल्यांकन के बाद ग्रेड दिखाई देगा।',

      'status.demo':           'डेमो डेटासेट',
      'status.placeholder':    'ML प्लेसहोल्डर',
      'status.apiPending':     'API लंबित',
      'status.open':           'खुला है',

      'chat.title':            'KisanLink सहायक',
      'chat.apiNotice':        'सहायक बैकएंड कनेक्ट नहीं है। उत्तर केवल डेमो हेतु हैं।',
      'chat.empty':            'फसल भाव, मंडी दर या खरीदार के बारे में पूछें।',
      'chat.placeholder':      'अपनी फसल या बाज़ार के बारे में पूछें...',
      'chat.send':             'भेजें',
      'chat.voiceStart':       'आवाज़ से पूछें (माइक)',
      'chat.voiceListening':   'सुन रहा हूँ... अब बोलें',
      'chat.voiceStop':        'सुनना बंद करें',
      'chat.voiceUnsupported': 'इस ब्राउज़र में आवाज़ इनपुट समर्थित नहीं है। आप लिखकर पूछ सकते हैं।',
      'chat.speakReply':       'उत्तर सुनें',
      'chat.q1':               'मुझे कहाँ बेचना चाहिए?',
      'chat.q2':               'वर्तमान बाज़ार मूल्य क्या है?',
      'chat.q3':               'क्या मुझे अभी बेचना चाहिए या इंतज़ार करना चाहिए?',
      'chat.q4':               'मेरे खरीदार अवसर दिखाएं',

      'ba.crop':               'फसल',
      'ba.quality':            'गुणवत्ता ग्रेड',
      'ba.location':           'स्थान',
      'ba.quantity':           'मात्रा',
      'ba.marketPrice':        'वर्तमान बाज़ार मूल्य',
      'ba.forecast':           '7-दिवसीय पूर्वानुमान',
      'ba.demand':             'खरीदार मांग',
      'ba.logistics':          'अनुमानित परिवहन खर्च',
      'ba.netRealisation':     'अनुमानित शुद्ध प्राप्ति',
      'ba.netNote':            'परिवहन और मंडी शुल्क घटाने के बाद शुद्ध प्राप्ति।',
      'ba.recLabel':           'अनुशंसित कार्यवाही',

      'profile.title':         'किसान प्रोफ़ाइल',
      'profile.contact':       'संपर्क',
      'profile.language':      'भाषा',
      'profile.switch':        'खाता बदलें'
    },

    mr: {
      'nav.overview':        'आढावा',
      'nav.saleLots':        'माझे विक्री लॉट',
      'nav.marketIntel':     'बाज़ार माहिती',
      'nav.recommendation':  'शिफारस',
      'nav.buyerMatches':    'खरेदीदार जुळणी',
      'nav.offers':          'प्राप्त ऑफर',
      'nav.transactions':    'व्यवहार',
      'nav.cropQuality':     'पीक गुणवत्ता तपासणी',
      'nav.priceOutlook':    'किंमत दृष्टीकोन',
      'nav.bestAction':      'सर्वोत्तम कृती',
      'topbar.createLot':    '+ विक्री लॉट तयार करा',
      'topbar.switchBuyer':  'खरेदीदार पोर्टलवर जा',
      'topbar.home':         'मुख्यपृष्ठ',

      'qa.title':            'शेतकरी जलद कृती',
      'qa.sellNow':          'आत्ता विका',
      'qa.wait':             'चांगल्या भावासाठी थांबा',
      'qa.compare':          'बाजारभाव तुलना करा',
      'qa.checkQuality':     'पीक गुणवत्ता तपासा',
      'qa.findBuyers':       'खरेदीदार शोधा',

      'section.bestAction':    'तुमच्या पिकासाठी सर्वोत्तम कृती',
      'section.priceOutlook':  'किंमत दृष्टीकोन आणि ७ दिवसांचा अंदाज',
      'section.marketCompare': 'जवळच्या बाज़ारांची तुलना करा',
      'section.buyerMatches':  'खरेदीदार संधी',
      'section.notifications': 'क्रियाकलाप आणि सूचना',
      'section.cropQuality':   'पीक गुणवत्ता तपासणी',
      'section.saleLots':      'सक्रिय विक्री लॉट',

      'action.sellNow':        'आत्ता विका',
      'action.wait':           'थांबा',
      'action.compare':        'बाज़ार तुलना करा',
      'action.analyze':        'गुणवत्ता विश्लेषण',
      'action.viewDetail':     'तपशील पहा',
      'action.makeOffer':      'ऑफर करा / पुनरावलोकन करा',
      'action.takePhoto':      'फोटो काढा',
      'action.uploadImage':    'फोटो अपलोड करा',
      'action.capture':        'फोटो घ्या',
      'action.retake':         'पुन्हा घ्या',
      'action.remove':         'काढून टाका',
      'action.browse':         'फाइल निवडा',
      'action.analyzeAgain':   'पुन्हा विश्लेषण करा',
      'action.applyPipeline':  'निर्णय प्रणालीमध्ये लागू करा',
      'action.getForecast':    'अंदाज मिळवा',
      'action.fetchMarkets':   'बाज़ारांची तुलना करा',

      'cqa.guide.title':       'उत्तम गुणवत्तेसाठी फोटो मार्गदर्शन',
      'cqa.guide.g1':          'फोटो चांगल्या नैसर्गिक प्रकाशात काढा.',
      'cqa.guide.g2':          'पीक कॅमेऱ्याच्या मध्यभागी स्पष्ट ठेवा.',
      'cqa.guide.g3':          'अस्पष्ट किंवा अंधुक फोटो टाळा.',
      'cqa.guide.g4':          'पिकाचा रंग आणि पोत स्पष्ट दिसू द्या.',

      'cqa.state.notAssessed': 'गुणवत्ता निकाल येथे दिसेल',
      'cqa.state.notAssessedSub': 'फोटो निवडा किंवा काढा आणि "गुणवत्ता विश्लेषण" वर क्लिक करा.',
      'cqa.state.assessing':   'पिकाच्या गुणवत्तेचे विश्लेषण होत आहे...',
      'cqa.state.assessingSub':'तपासणी सुरू आहे. कृपया थोडा वेळ थांबा.',
      'cqa.state.gradeLabel':  'अंदाजे ग्रेड',
      'cqa.state.confLabel':   'मॉडेल अचूकता',
      'cqa.state.indicators':  'गुणवत्ता निर्देशक',
      'cqa.state.placeholder': 'ML सेवेशी जोडणीची प्रतीक्षा',
      'cqa.state.placeholderMsg': 'ML सेवा जोडल्यावर गुणवत्ता विश्लेषण उपलब्ध होईल.',
      'cqa.state.gradePending':'गुणवत्ता तपासणीनंतर ग्रेड दिसेल.',

      'status.demo':           'डेमो डेटासेट',
      'status.placeholder':    'ML प्लेसहोल्डर',
      'status.apiPending':     'API प्रलंबित',
      'status.open':           'खुले',

      'chat.title':            'KisanLink सहाय्यक',
      'chat.apiNotice':        'सहाय्यक बॅकएंड जोडलेले नाही. उत्तरे फक्त डेमोसाठी आहेत.',
      'chat.empty':            'पीक भाव, बाजार किंवा खरेदीदारांबद्दल विचारा.',
      'chat.placeholder':      'तुमच्या पीक किंवा बाज़ाराबद्दल विचारा...',
      'chat.send':             'पाठवा',
      'chat.voiceStart':       'आवाजाने बोला (माईक)',
      'chat.voiceListening':   'ऐकत आहे... आता बोला',
      'chat.voiceStop':        'ऐकणे थांबवा',
      'chat.voiceUnsupported': 'या ब्राउझरमध्ये व्हॉइस इनपुट उपलब्ध नाही. लिहून विचारा.',
      'chat.speakReply':       'उत्तर ऐका',
      'chat.q1':               'मी कुठे विकावे?',
      'chat.q2':               'सध्याची बाज़ार किंमत काय आहे?',
      'chat.q3':               'मी आत्ता विकावे की थांबावे?',
      'chat.q4':               'माझ्या खरेदीदार संधी दाखवा',

      'ba.crop':               'पीक',
      'ba.quality':            'गुणवत्ता ग्रेड',
      'ba.location':           'स्थान',
      'ba.quantity':           'प्रमाण',
      'ba.marketPrice':        'चालू बाजारभाव',
      'ba.forecast':           '७ दिवसांचा अंदाज',
      'ba.demand':             'खरेदीदार मागणी',
      'ba.logistics':          'वाहतूक खर्च',
      'ba.netRealisation':     'अंदाजे निव्वळ नफा',
      'ba.netNote':            'वाहतूक व बाजार शुल्क वजा केल्यानंतर निव्वळ उत्पन्न.',
      'ba.recLabel':           'शिफारस केलेली कृती',

      'profile.title':         'शेतकरी प्रोफाइल',
      'profile.contact':       'संपर्क',
      'profile.language':      'भाषा',
      'profile.switch':        'खाते बदला'
    },

    gu: {
      'nav.overview':        'ઝાંખી',
      'nav.saleLots':        'મારા વેચાણ લોટ',
      'nav.marketIntel':     'બજાર માહિતી',
      'nav.recommendation':  'ભલામણ',
      'nav.buyerMatches':    'ખરીદનાર મેળ',
      'nav.offers':          'મળેલ ઓફર્સ',
      'nav.transactions':    'વ્યવહારો',
      'nav.cropQuality':     'પાક ગુણવત્તા તપાસ',
      'nav.priceOutlook':    'ભાવ દૃષ્ટિકોણ',
      'nav.bestAction':      'શ્રેષ્ઠ નિર્ણય',
      'topbar.createLot':    '+ વેચાણ લોટ બનાવો',
      'topbar.switchBuyer':  'ખરીદનાર પોર્ટલ',
      'topbar.home':         'હોમ',

      'qa.title':            'ખેડૂત ઝડપી ક્રિયાઓ',
      'qa.sellNow':          'હમણાં વેચો',
      'qa.wait':             'વધુ સારા ભાવ માટે રાહ જુઓ',
      'qa.compare':          'બજાર સરખામણી કરો',
      'qa.checkQuality':     'ગુણવત્તા તપાસો',
      'qa.findBuyers':       'ખરીદદારો શોધો',

      'section.bestAction':    'તમારા પાક માટે શ્રેષ્ઠ કાર્યવાહી',
      'section.priceOutlook':  'ભાવ દૃષ્ટિકોણ અને ૭ દિવસનો અંદાજ',
      'section.marketCompare': 'નજીકના બજારોની સરખામણી',
      'section.buyerMatches':  'ખરીદનાર તકો',
      'section.notifications': 'સૂચનાઓ અને પ્રવૃત્તિ',
      'section.cropQuality':   'પાક ગુણવત્તા ચકાસણી',
      'section.saleLots':      'સક્રિય વેચાણ લોટ',

      'action.sellNow':        'હમણાં વેચો',
      'action.wait':           'રાહ જુઓ',
      'action.compare':        'બજાર સરખાવો',
      'action.analyze':        'ગુણવત્તા વિશ્લેષણ',
      'action.viewDetail':     'વિગત જુઓ',
      'action.makeOffer':      'ઓફર જુઓ / કરો',
      'action.takePhoto':      'ફોટો પાડો',
      'action.uploadImage':    'ફોટો અપલોડ કરો',
      'action.capture':        'ફોટો લો',
      'action.retake':         'ફરીથી લો',
      'action.remove':         'દૂર કરો',
      'action.browse':         'ફાઇલ પસંદ કરો',
      'action.analyzeAgain':   'ફરી તપાસો',
      'action.applyPipeline':  'નિર્ણય પ્રક્રિયામાં ઉમેરો',
      'action.getForecast':    'અંદાજ મેળવો',
      'action.fetchMarkets':   'બજાર સરખાવો',

      'cqa.guide.title':       'સારી ગુણવત્તા માટે ફોટો માર્ગદર્શન',
      'cqa.guide.g1':          'કુદરતી પ્રકાશમાં ફોટો પાડો (પડછાયા ટાળો).',
      'cqa.guide.g2':          'પાક કેમેરાની વચ્ચે સ્પષ્ટ રાખો.',
      'cqa.guide.g3':          'ધૂંધળા કે અંધારા ફોટા ટાળો.',
      'cqa.guide.g4':          'પાકનો રંગ અને કદ સ્પષ્ટ દેખાય તેમ રાખો.',

      'cqa.state.notAssessed': 'ગુણવત્તા પરિણામ અહીં દેખાશે',
      'cqa.state.notAssessedSub': 'ફોટો પસંદ કરો અને "ગુણવત્તા વિશ્લેષણ" પર ક્લિક કરો.',
      'cqa.state.assessing':   'ગુણવત્તા વિશ્લેષણ ચાલુ છે...',
      'cqa.state.assessingSub':'છબી મોકલાઈ રહી છે, કૃપા કરીને રાહ જુઓ.',
      'cqa.state.gradeLabel':  'અંદાજિત ગ્રેડ',
      'cqa.state.confLabel':   'વિશ્વાસ સ્તર',
      'cqa.state.indicators':  'ગુણવત્તા લક્ષણો',
      'cqa.state.placeholder': 'ML સેવા કનેક્શન બાકી',
      'cqa.state.placeholderMsg': 'ML સેવા જોડાશે ત્યારે વિશ્લેષણ દેખાશે.',
      'cqa.state.gradePending':'ગુણવત્તા તપાસ પછી ગ્રેડ દેખાશે.',

      'status.demo':           'ડેમો ડેટાસેટ',
      'status.placeholder':    'ML પ્લેસહોલ્ડર',
      'status.apiPending':     'API બાકી',
      'status.open':           'ખુલ્લું',

      'chat.title':            'KisanLink સહાયક',
      'chat.apiNotice':        'સહાયક બેકએન્ડ જોડાયેલ નથી. જવાબો માત્ર ડેમો છે.',
      'chat.empty':            'પાકના ભાવ, બજાર કે ખરીદદારો વિશે પૂછો.',
      'chat.placeholder':      'તમારા પાક કે બજાર વિશે પૂછો...',
      'chat.send':             'મોકલો',
      'chat.voiceStart':       'અવાજથી પૂછો (માઇક)',
      'chat.voiceListening':   'સાંભળી રહ્યો છું... હવે બોલો',
      'chat.voiceStop':        'સાંભળવાનું બંધ કરો',
      'chat.voiceUnsupported': 'આ બ્રાઉઝરમાં વોઇસ ઇનપુટ સપોર્ટેડ નથી.',
      'chat.speakReply':       'જવાબ સાંભળો',
      'chat.q1':               'મારે ક્યાં વેચવું જોઈએ?',
      'chat.q2':               'હાલનો બજાર ભાવ શું છે?',
      'chat.q3':               'હમણાં વેચવું કે રાહ જોવી?',
      'chat.q4':               'ખરીદદાર તકો બતાવો',

      'ba.crop':               'પાક',
      'ba.quality':            'ગુણવત્તા ગ્રેડ',
      'ba.location':           'સ્થળ',
      'ba.quantity':           'જથ્થો',
      'ba.marketPrice':        'હાલનો ભાવ',
      'ba.forecast':           '૭ દિવસનો અંદાજ',
      'ba.demand':             'ખરીદદાર માંગ',
      'ba.logistics':          'પરિવહન ખર્ચ',
      'ba.netRealisation':     'ચોખ્ખી આવક',
      'ba.netNote':            'પરિવહન અને ખર્ચ બાદ કર્યા પછી ચોખ્ખી રકમ.',
      'ba.recLabel':           'ભલામણ કરેલ પગલું',

      'profile.title':         'ખેડૂત પ્રોફાઇલ',
      'profile.contact':       'સંપર્ક',
      'profile.language':      'ભાષા',
      'profile.switch':        'ખાતું બદલો'
    },

    pa: {
      'nav.overview':        'ਸੰਖੇਪ',
      'nav.saleLots':        'ਮੇਰੇ ਵਿਕਰੀ ਲਾਟ',
      'nav.marketIntel':     'ਮੰਡੀ ਜਾਣਕਾਰੀ',
      'nav.recommendation':  'ਸਿਫਾਰਸ਼',
      'nav.buyerMatches':    'ਖਰੀਦਦਾਰ ਮੇਲ',
      'nav.offers':          'ਪ੍ਰਾਪਤ ਆਫਰ',
      'nav.transactions':    'ਲੈਣ-ਦੇਣ',
      'nav.cropQuality':     'ਫਸਲ ਗੁਣਵੱਤਾ ਜਾਂਚ',
      'nav.priceOutlook':    'ਭਾਅ ਦ੍ਰਿਸ਼ਟੀਕੋਣ',
      'nav.bestAction':      'ਸਭ ਤੋਂ ਵਧੀਆ ਕਦਮ',
      'topbar.createLot':    '+ ਨਵਾਂ ਲਾਟ ਬਣਾਓ',
      'topbar.switchBuyer':  'ਖਰੀਦਦਾਰ ਪੋਰਟਲ',
      'topbar.home':         'ਮੁੱਖ ਪੰਨਾ',

      'qa.title':            'ਕਿਸਾਨ ਤੁਰੰਤ ਕਦਮ',
      'qa.sellNow':          'ਹੁਣੇ ਵੇਚੋ',
      'qa.wait':             'ਚੰਗੇ ਭਾਅ ਲਈ ਉਡੀਕੋ',
      'qa.compare':          'ਮੰਡੀਆਂ ਦੀ ਤੁਲਨਾ',
      'qa.checkQuality':     'ਗੁਣਵੱਤਾ ਪਰਖੋ',
      'qa.findBuyers':       'ਖਰੀਦਦਾਰ ਲੱਭੋ',

      'section.bestAction':    'ਤੁਹਾਡੀ ਫਸਲ ਲਈ ਸਭ ਤੋਂ ਵਧੀਆ ਫੈਸਲਾ',
      'section.priceOutlook':  'ਮੁੱਲ ਦ੍ਰਿਸ਼ਟੀਕੋਣ ਅਤੇ 7-ਦਿਨ ਦਾ ਅੰਦਾਜ਼ਾ',
      'section.marketCompare': 'ਨੇੜਲੀਆਂ ਮੰਡੀਆਂ ਦੀ ਤੁਲਨਾ',
      'section.buyerMatches':  'ਖਰੀਦਦਾਰ ਮੌਕੇ',
      'section.notifications': 'ਸੂਚਨਾਵਾਂ',
      'section.cropQuality':   'ਫਸਲ ਗੁਣਵੱਤਾ ਚੈੱਕ',
      'section.saleLots':      'ਸਰਗਰਮ ਵਿਕਰੀ ਲਾਟ',

      'action.sellNow':        'ਹੁਣੇ ਵੇਚੋ',
      'action.wait':           'ਉਡੀਕ ਕਰੋ',
      'action.compare':        'ਮੰਡੀ ਤੁਲਨਾ',
      'action.analyze':        'ਗੁਣਵੱਤਾ ਜਾਂਚੋ',
      'action.viewDetail':     'ਵੇਰਵਾ ਦੇਖੋ',
      'action.makeOffer':      'ਆਫਰ ਦੇਖੋ',
      'action.takePhoto':      'ਫੋਟੋ ਖਿੱਚੋ',
      'action.uploadImage':    'ਤਸਵੀਰ ਅਪਲੋਡ ਕਰੋ',
      'action.capture':        'ਫੋਟੋ ਲਵੋ',
      'action.retake':         'ਦੁਬਾਰਾ ਲਵੋ',
      'action.remove':         'ਹਟਾਓ',
      'action.browse':         'ਫਾਈਲ ਚੁਣੋ',
      'action.analyzeAgain':   'ਮੁੜ ਜਾਂਚ ਕਰੋ',
      'action.applyPipeline':  'ਫੈਸਲੇ ਵਿੱਚ ਲਾਗੂ ਕਰੋ',
      'action.getForecast':    'ਅੰਦਾਜ਼ਾ ਪ੍ਰਾਪਤ ਕਰੋ',
      'action.fetchMarkets':   'ਮੰਡੀਆਂ ਤੁਲਨਾ ਕਰੋ',

      'cqa.guide.title':       'ਵਧੀਆ ਨਤੀਜਿਆਂ ਲਈ ਫੋਟੋ ਸਲਾਹ',
      'cqa.guide.g1':          'ਫੋਟੋ ਚੰਗੀ ਕੁਦਰਤੀ ਰੋਸ਼ਨੀ ਵਿੱਚ ਲਓ।',
      'cqa.guide.g2':          'ਫਸਲ ਨੂੰ ਕੈਮਰੇ ਦੇ ਵਿਚਕਾਰ ਸਾਫ ਰੱਖੋ।',
      'cqa.guide.g3':          'ਧੁੰਦਲੀਆਂ ਫੋਟੋਆਂ ਤੋਂ ਬਚੋ।',
      'cqa.guide.g4':          'ਫਸਲ ਦਾ ਰੰਗ ਅਤੇ ਆਕਾਰ ਸਾਫ਼ ਦਿਖਣਾ ਚਾਹੀਦਾ ਹੈ।',

      'cqa.state.notAssessed': 'ਗੁਣਵੱਤਾ ਨਤੀਜਾ ਇੱਥੇ ਆਵੇਗਾ',
      'cqa.state.notAssessedSub': 'ਫੋਟੋ ਚੁਣੋ ਅਤੇ "ਗੁਣਵੱਤਾ ਜਾਂਚੋ" ਤੇ ਕਲਿੱਕ ਕਰੋ।',
      'cqa.state.assessing':   'ਗੁਣਵੱਤਾ ਜਾਂਚ ਜਾਰੀ ਹੈ...',
      'cqa.state.assessingSub':'ਤਸਵੀਰ ਭੇਜੀ ਜਾ ਰਹੀ ਹੈ, ਕਿਰਪਾ ਕਰਕੇ ਉਡੀਕ ਕਰੋ।',
      'cqa.state.gradeLabel':  'ਅੰਦਾਜ਼ਨ ਗ੍ਰੇਡ',
      'cqa.state.confLabel':   'ਭਰੋਸੇਯੋਗਤਾ',
      'cqa.state.indicators':  'ਗੁਣਵੱਤਾ ਸੰਕੇਤਕ',
      'cqa.state.placeholder': 'ML ਕਨੈਕਸ਼ਨ ਬਾਕੀ',
      'cqa.state.placeholderMsg': 'ਸੇਵਾ ਜੁੜਨ ਤੇ ਗੁਣਵੱਤਾ ਨਤੀਜੇ ਦਿਖਣਗੇ।',
      'cqa.state.gradePending':'ਜਾਂਚ ਤੋਂ ਬਾਅਦ ਗ੍ਰੇਡ ਮਿਲੇਗਾ।',

      'status.demo':           'ਡੈਮੋ ਡਾਟਾਸੈੱਟ',
      'status.placeholder':    'ML ਪਲੇਸਹੋਲਡਰ',
      'status.apiPending':     'API ਬਾਕੀ',
      'status.open':           'ਖੁੱਲ੍ਹਾ',

      'chat.title':            'KisanLink ਸਹਾਇਕ',
      'chat.apiNotice':        'ਸਹਾਇਕ ਜੁੜਿਆ ਨਹੀਂ ਹੈ। ਜਵਾਬ ਸਿਰਫ ਡੈਮੋ ਹਨ।',
      'chat.empty':            'ਫਸਲ ਭਾਅ ਜਾਂ ਮੰਡੀ ਬਾਰੇ ਪੁੱਛੋ।',
      'chat.placeholder':      'ਆਪਣੀ ਫਸਲ ਜਾਂ ਮੰਡੀ ਬਾਰੇ ਪੁੱਛੋ...',
      'chat.send':             'ਭੇਜੋ',
      'chat.voiceStart':       'ਬੋਲ ਕੇ ਪੁੱਛੋ (ਮਾਈਕ)',
      'chat.voiceListening':   'ਸੁਣ ਰਿਹਾ ਹਾਂ... ਹੁਣ ਬੋਲੋ',
      'chat.voiceStop':        'ਸੁਣਨਾ ਬੰਦ ਕਰੋ',
      'chat.voiceUnsupported': 'ਇਸ ਬ੍ਰਾਊਜ਼ਰ ਵਿੱਚ ਵੌਇਸ ਇਨਪੁਟ ਨਹੀਂ ਚੱਲਦਾ।',
      'chat.speakReply':       'ਜਵਾਬ ਸੁਣੋ',
      'chat.q1':               'ਮੈਨੂੰ ਕਿੱਥੇ ਵੇਚਣਾ ਚਾਹੀਦਾ ਹੈ?',
      'chat.q2':               'ਮੌਜੂਦਾ ਮੰਡੀ ਭਾਅ ਕੀ ਹੈ?',
      'chat.q3':               'ਹੁਣੇ ਵੇਚਾਂ ਜਾਂ ਉਡੀਕਾਂ?',
      'chat.q4':               'ਖਰੀਦਦਾਰ ਦਿਖਾਓ',

      'ba.crop':               'ਫਸਲ',
      'ba.quality':            'ਗ੍ਰੇਡ',
      'ba.location':           'ਸਥਾਨ',
      'ba.quantity':           'ਮਾਤਰਾ',
      'ba.marketPrice':        'ਮੌਜੂਦਾ ਭਾਅ',
      'ba.forecast':           '7-ਦਿਨ ਅੰਦਾਜ਼ਾ',
      'ba.demand':             'ਮੰਗ',
      'ba.logistics':          'ਢੋਆ-ਢੁਆਈ ਖਰਚ',
      'ba.netRealisation':     'ਕੁੱਲ ਮੁਨਾਫਾ',
      'ba.netNote':            'ਸਾਰੇ ਖਰਚੇ ਕੱਟ ਕੇ ਸ਼ੁੱਧ ਆਮਦਨ।',
      'ba.recLabel':           'ਸਿਫਾਰਸ਼',

      'profile.title':         'ਕਿਸਾਨ ਪ੍ਰੋਫਾਈਲ',
      'profile.contact':       'ਸੰਪਰਕ',
      'profile.language':      'ਭਾਸ਼ਾ',
      'profile.switch':        'ਖਾਤਾ ਬਦਲੋ'
    },

    bn: {
      'nav.overview':        'সারসংক্ষেপ',
      'nav.saleLots':        'আমার বিক্রয় লট',
      'nav.marketIntel':     'বাজার তথ্য',
      'nav.recommendation':  'পরামর্শ',
      'nav.buyerMatches':    'ক্রেতা মিল',
      'nav.offers':          'প্রাপ্ত অফার',
      'nav.transactions':    'লেনদেন',
      'nav.cropQuality':     'ফসলের মান যাচাই',
      'nav.priceOutlook':    'দামের পূর্বাভাস',
      'nav.bestAction':      'সেরা সিদ্ধান্ত',
      'topbar.createLot':    '+ বিক্রয় লট তৈরি করুন',
      'topbar.switchBuyer':  'ক্রেতা পোর্টাল',
      'topbar.home':         'হোম',

      'qa.title':            'কৃষক দ্রুত পদক্ষেপ',
      'qa.sellNow':          'এখনই বিক্রি করুন',
      'qa.wait':             'ভালো দামের জন্য অপেক্ষা করুন',
      'qa.compare':          'বাজার তুলনা করুন',
      'qa.checkQuality':     'মান যাচাই করুন',
      'qa.findBuyers':       'ক্রেতা খুঁজুন',

      'section.bestAction':    'আপনার ফসলের জন্য সেরা পদক্ষেপ',
      'section.priceOutlook':  'মূল্য পূর্বাভাস ও ৭ দিনের ট্রেন্ড',
      'section.marketCompare': 'কাছের বাজারগুলোর তুলনা',
      'section.buyerMatches':  'ক্রেতার সুযোগ',
      'section.notifications': 'কার্যক্রম ও বিজ্ঞপ্তি',
      'section.cropQuality':   'ফসলের গুণমান পরীক্ষা',
      'section.saleLots':      'সক্রিয় বিক্রয় লট',

      'action.sellNow':        'এখনই বিক্রি করুন',
      'action.wait':           'অপেক্ষা করুন',
      'action.compare':        'বাজার তুলনা',
      'action.analyze':        'মান বিশ্লেষণ',
      'action.viewDetail':     'বিস্তারিত দেখুন',
      'action.makeOffer':      'অফার পর্যালোচনা',
      'action.takePhoto':      'ছবি তুলুন',
      'action.uploadImage':    'ছবি আপলোড করুন',
      'action.capture':        'ক্যাপচার করুন',
      'action.retake':         'আবার নিন',
      'action.remove':         'মুছুন',
      'action.browse':         'ফাইল বাছাই করুন',
      'action.analyzeAgain':   'পুনরায় বিশ্লেষণ',
      'action.applyPipeline':  'সিদ্ধান্ত ইঞ্জিনে প্রয়োগ করুন',
      'action.getForecast':    'পূর্বাভাস দেখুন',
      'action.fetchMarkets':   'বাজার তুলনা',

      'cqa.guide.title':       'ভালো ফলাফলের জন্য ছবি তোলার নিয়ম',
      'cqa.guide.g1':          'উজ্জ্বল প্রাকৃতিক আলোতে ছবি তুলুন।',
      'cqa.guide.g2':          'ফসলটি ফ্রেমের মাঝখানে স্পষ্টভাবে রাখুন।',
      'cqa.guide.g3':          'অস্পষ্ট বা অন্ধকার ছবি এড়িয়ে চলুন।',
      'cqa.guide.g4':          'ফসলের আকার ও রঙ পরিষ্কারভাবে দেখান।',

      'cqa.state.notAssessed': 'গুণমান ফলাফল এখানে প্রদর্শিত হবে',
      'cqa.state.notAssessedSub': 'ছবি নির্বাচন করে "মান বিশ্লেষণ"-এ ক্লিক করুন।',
      'cqa.state.assessing':   'মান বিশ্লেষণ চলছে...',
      'cqa.state.assessingSub':'ছবি পাঠানো হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন।',
      'cqa.state.gradeLabel':  'আনুমানিক গ্রেড',
      'cqa.state.confLabel':   'মডেল নির্ভুলতা',
      'cqa.state.indicators':  'গুণমান সূচক',
      'cqa.state.placeholder': 'ML সংযোগের অপেক্ষায়',
      'cqa.state.placeholderMsg': 'ML সেবা সংযুক্ত হলে মান যাচাই দৃশ্যমান হবে।',
      'cqa.state.gradePending':'মান মূল্যায়নের পর গ্রেড প্রদর্শিত হবে।',

      'status.demo':           'ডেমো ডেটাসেট',
      'status.placeholder':    'ML স্থানধারক',
      'status.apiPending':     'API অপেক্ষমান',
      'status.open':           'উন্মুক্ত',

      'chat.title':            'KisanLink সহকারী',
      'chat.apiNotice':        'সহকারী ব্যাকএন্ড সংযুক্ত নয়। উত্তরগুলো ডেমো মাত্র।',
      'chat.empty':            'ফসলের দর বা বাজার সম্পর্কে জিজ্ঞাসা করুন।',
      'chat.placeholder':      'আপনার ফসল বা বাজার সম্পর্কে জিজ্ঞাসা করুন...',
      'chat.send':             'পাঠান',
      'chat.voiceStart':       'ভয়েসে বলুন (মাইক)',
      'chat.voiceListening':   'শুনছি... এখন কথা বলুন',
      'chat.voiceStop':        'শোনা বন্ধ করুন',
      'chat.voiceUnsupported': 'এই ব্রাউজারে ভয়েস ইনপুট সমর্থিত নয়।',
      'chat.speakReply':       'উত্তর শুনুন',
      'chat.q1':               'আমার কোথায় বিক্রি করা উচিত?',
      'chat.q2':               'বর্তমান বাজার দর কত?',
      'chat.q3':               'এখন বিক্রি করব নাকি অপেক্ষা করব?',
      'chat.q4':               'ক্রেতাদের তালিকা দেখান',

      'ba.crop':               'ফসল',
      'ba.quality':            'গ্রেড',
      'ba.location':           'অবস্থান',
      'ba.quantity':           'পরিমাণ',
      'ba.marketPrice':        'বর্তমান দর',
      'ba.forecast':           '৭ দিনের পূর্বাভাস',
      'ba.demand':             'চাহিদা',
      'ba.logistics':          'পরিবহন খরচ',
      'ba.netRealisation':     'প্রত্যাশিত নিট প্রাপ্তি',
      'ba.netNote':            'পরিবহন ও বাজার খরচ বাদ দেওয়ার পর নিট মূল্য।',
      'ba.recLabel':           'পরামর্শ',

      'profile.title':         'কৃষক প্রোফাইল',
      'profile.contact':       'যোগাযোগ',
      'profile.language':      'ভাষা',
      'profile.switch':        'অ্যাকাউন্ট পরিবর্তন'
    },

    ta: {
      'nav.overview':        'மேலோட்டம்',
      'nav.saleLots':        'என் விற்பனை குவியல்கள்',
      'nav.marketIntel':     'சந்தை நிலவரம்',
      'nav.recommendation':  'பரிந்துரை',
      'nav.buyerMatches':    'வாங்குபவர் பொருத்தம்',
      'nav.offers':          'வந்த சலுகைகள்',
      'nav.transactions':    'பரிவர்த்தனைகள்',
      'nav.cropQuality':     'பயிர் தரம் பார்த்தல்',
      'nav.priceOutlook':    'விலை நிலவரம்',
      'nav.bestAction':      'சிறந்த செயல்',
      'topbar.createLot':    '+ விற்பனை குவியல் சேர்க்க',
      'topbar.switchBuyer':  'வாங்குபவர் தளம்',
      'topbar.home':         'முகப்பு',

      'qa.title':            'விவசாயி விரைவு செயல்கள்',
      'qa.sellNow':          'இப்போதே விற்கவும்',
      'qa.wait':             'நல்ல விலைக்காக காத்திருக்கவும்',
      'qa.compare':          'சந்தைகளை ஒப்பிடவும்',
      'qa.checkQuality':     'தரத்தை சோதிக்கவும்',
      'qa.findBuyers':       'வாங்குபவர்களை கண்டறியவும்',

      'section.bestAction':    'உங்கள் பயிருக்கான சிறந்த செயல்',
      'section.priceOutlook':  'விலை பார்வை & 7 நாள் கணிப்பு',
      'section.marketCompare': 'அருகிலுள்ள சந்தைகளை ஒப்பிடுக',
      'section.buyerMatches':  'வாங்குபவர் வாய்ப்புகள்',
      'section.notifications': 'செயல்பாடுகள் & அறிவிப்புகள்',
      'section.cropQuality':   'பயிர் தர பரிசோதனை',
      'section.saleLots':      'செயலில் உள்ள விற்பனை குவியல்கள்',

      'action.sellNow':        'இப்போதே விற்கவும்',
      'action.wait':           'காத்திருக்கவும்',
      'action.compare':        'சந்தையை ஒப்பிடுக',
      'action.analyze':        'தரம் ஆராய்க',
      'action.viewDetail':     'விவரம் பார்க்க',
      'action.makeOffer':      'சலுகை பார்க்க',
      'action.takePhoto':      'புகைப்படம் எடுக்க',
      'action.uploadImage':    'படம் பதிவேற்ற',
      'action.capture':        'படம் எடுக்க',
      'action.retake':         'மீண்டும் எடுக்க',
      'action.remove':         'நீக்குக',
      'action.browse':         'கோப்பைத் தேர்வுசெய்க',
      'action.analyzeAgain':   'மீண்டும் ஆராய்க',
      'action.applyPipeline':  'முடிவு இயந்திரத்தில் சேர்க்க',
      'action.getForecast':    'கணிப்பை பெறுக',
      'action.fetchMarkets':   'சந்தைகளை ஒப்பிடுக',

      'cqa.guide.title':       'சிறந்த முடிவுகளுக்கான பட வழிகாட்டுதல்',
      'cqa.guide.g1':          'இயற்கை வெளிச்சத்தில் படம் எடுக்கவும்.',
      'cqa.guide.g2':          'பயிரை தெளிவாக மையத்தில் வைக்கவும்.',
      'cqa.guide.g3':          'மங்கலான படங்களை தவிர்க்கவும்.',
      'cqa.guide.g4':          'பயிரின் நிறம் மற்றும் அமைப்பை தெளிவாகக் காட்டவும்.',

      'cqa.state.notAssessed': 'தர முடிவு இங்கே தோன்றும்',
      'cqa.state.notAssessedSub': 'படத்தைத் தேர்ந்தெடுத்து "தரம் ஆராய்க" என்பதைக் கிளிக் செய்யவும்.',
      'cqa.state.assessing':   'தரம் பரிசோதிக்கப்படுகிறது...',
      'cqa.state.assessingSub':'படம் அனுப்பப்படுகிறது, சிறிது காத்திருக்கவும்.',
      'cqa.state.gradeLabel':  'மதிப்பிடப்பட்ட தரம்',
      'cqa.state.confLabel':   'துல்லியம்',
      'cqa.state.indicators':  'தரக் குறிகாட்டிகள்',
      'cqa.state.placeholder': 'ML இணைப்பு நிலுவையில் உள்ளது',
      'cqa.state.placeholderMsg': 'ML சேவை இணைக்கப்பட்டதும் தரம் தோன்றும்.',
      'cqa.state.gradePending':'தர பரிசோதனைக்குப் பின் கிரேடு தோன்றும்.',

      'status.demo':           'டெமோ தகவல்',
      'status.placeholder':    'ML மாதிரி',
      'status.apiPending':     'API நிலுவை',
      'status.open':           'திறந்தநிலை',

      'chat.title':            'KisanLink உதவியாளர்',
      'chat.apiNotice':        'உதவியாளர் சேவை இணைக்கப்படவில்லை. பதில்கள் டெமோ மட்டுமே.',
      'chat.empty':            'பயிர் விலை அல்லது சந்தை பற்றி கேளுங்கள்.',
      'chat.placeholder':      'உங்கள் பயிர் அல்லது சந்தை பற்றி கேளுங்கள்...',
      'chat.send':             'அனுப்புக',
      'chat.voiceStart':       'குரல் மூலம் கேட்க (மைக்)',
      'chat.voiceListening':   'கேட்கிறது... இப்போது பேசுங்கள்',
      'chat.voiceStop':        'நிறுத்துக',
      'chat.voiceUnsupported': 'இந்த உலாவியில் குரல் உள்ளீடு ஆதரிக்கப்படவில்லை.',
      'chat.speakReply':       'பதிலை கேட்க',
      'chat.q1':               'நான் எங்கு விற்க வேண்டும்?',
      'chat.q2':               'தற்போதைய சந்தை விலை என்ன?',
      'chat.q3':               'இப்போது விற்கலாமா அல்லது காத்திருக்கலாமா?',
      'chat.q4':               'வாங்குபவர் வாய்ப்புகளைக் காட்டு',

      'ba.crop':               'பயிர்',
      'ba.quality':            'தர கிரேடு',
      'ba.location':           'இடம்',
      'ba.quantity':           'அளவு',
      'ba.marketPrice':        'சந்தை விலை',
      'ba.forecast':           '7 நாள் கணிப்பு',
      'ba.demand':             'வாங்குபவர் தேவை',
      'ba.logistics':          'போக்குவரத்து செலவு',
      'ba.netRealisation':     'எதிர்பார்க்கப்படும் நிகர வரவு',
      'ba.netNote':            'போக்குவரத்து கழித்து நிகர வரவு.',
      'ba.recLabel':           'பரிந்துரைக்கப்பட்ட செயல்',

      'profile.title':         'விவசாயி சுயவிவரம்',
      'profile.contact':       'தொடர்பு',
      'profile.language':      'மொழி',
      'profile.switch':        'கணக்கு மாற்ற'
    },

    te: {
      'nav.overview':        'అవలోకనం',
      'nav.saleLots':        'నా విక్రయ లాట్లు',
      'nav.marketIntel':     'మార్కెట్ సమాచారం',
      'nav.recommendation':  'సిఫార్సు',
      'nav.buyerMatches':    'కొనుగోలుదారుల మ్యాచ్',
      'nav.offers':          'వచ్చిన ఆఫర్లు',
      'nav.transactions':    'లావాదేవీలు',
      'nav.cropQuality':     'పంట నాణ్యత తనిఖీ',
      'nav.priceOutlook':    'ధర దృక్పథం',
      'nav.bestAction':      'ఉత్తమ కార్యాచరణ',
      'topbar.createLot':    '+ విక్రయ లాట్ సృష్టించండి',
      'topbar.switchBuyer':  'కొనుగోలుదారు పోర్టల్',
      'topbar.home':         'హోమ్',

      'qa.title':            'రైతు త్వరిత చర్యలు',
      'qa.sellNow':          'ఇప్పుడే అమ్మండి',
      'qa.wait':             'మంచి ధర కోసం వేచి ఉండండి',
      'qa.compare':          'మార్కెట్లను పోల్చండి',
      'qa.checkQuality':     'నాణ్యత తనిఖీ చేయండి',
      'qa.findBuyers':       'కొనుగోలుదారులను కనుగొనండి',

      'section.bestAction':    'మీ పంటకు అత్యుత్తమ నిర్ణయం',
      'section.priceOutlook':  'ధరల దృక్పథం & 7 రోజుల అంచనా',
      'section.marketCompare': 'సమీప మార్కెట్లను పోల్చండి',
      'section.buyerMatches':  'కొనుగోలుదారు అవకాశాలు',
      'section.notifications': 'కార్యకలాపాలు & నోటిఫికేషన్లు',
      'section.cropQuality':   'పంట నాణ్యత తనిఖీ',
      'section.saleLots':      'యాక్టివ్ విక్రయ లాట్లు',

      'action.sellNow':        'ఇప్పుడే అమ్మండి',
      'action.wait':           'వేచి ఉండండి',
      'action.compare':        'మార్కెట్ పోల్చండి',
      'action.analyze':        'నాణ్యత విశ్లేషణ',
      'action.viewDetail':     'వివరాలు చూడండి',
      'action.makeOffer':      'ఆఫర్ చేయండి / సమీక్షించండి',
      'action.takePhoto':      'ఫోటో తీయండి',
      'action.uploadImage':    'చిత్రాన్ని అప్‌లోడ్ చేయండి',
      'action.capture':        'ఫోటో తీయండి',
      'action.retake':         'మళ్ళీ తీయండి',
      'action.remove':         'తొలగించండి',
      'action.browse':         'ఫైల్ ఎంచుకోండి',
      'action.analyzeAgain':   'మళ్ళీ విశ్లేషించండి',
      'action.applyPipeline':  'నిర్ణయ ఇంజిన్‌కు వర్తింపజేయండి',
      'action.getForecast':    'అంచనా పొందండి',
      'action.fetchMarkets':   'మార్కెట్లను పోల్చండి',

      'cqa.guide.title':       'ఖచ్చితమైన నాణ్యత కోసం ఫోటో సూచనలు',
      'cqa.guide.g1':          'సహజ కాంతిలో ఫోటో తీయండి.',
      'cqa.guide.g2':          'పంటను స్పష్టంగా మధ్యలో ఉంచండి.',
      'cqa.guide.g3':          'మసకబారిన ఫోటోలను నివారించండి.',
      'cqa.guide.g4':          'రంగు మరియు పరిమాణం స్పష్టంగా కనిపించాలి.',

      'cqa.state.notAssessed': 'నాణ్యత ఫలితం ఇక్కడ కనిపిస్తుంది',
      'cqa.state.notAssessedSub': 'ఫోటోను ఎంచుకుని "నాణ్యత విశ్లేషణ" పై క్లిక్ చేయండి.',
      'cqa.state.assessing':   'నాణ్యత విశ్లేషణ జరుగుతోంది...',
      'cqa.state.assessingSub':'చిత్రం పంపబడుతోంది, దయచేసి వేచి ఉండండి.',
      'cqa.state.gradeLabel':  'అంచనా వేసిన గ్రేడ్',
      'cqa.state.confLabel':   'విశ్వసనీయత',
      'cqa.state.indicators':  'నాణ్యత సూచికలు',
      'cqa.state.placeholder': 'ML కనెక్షన్ కోసం నిరీక్షణ',
      'cqa.state.placeholderMsg': 'ML సేవ కనెక్ట్ అయినప్పుడు నాణ్యత కనిపిస్తుంది.',
      'cqa.state.gradePending':'నాణ్యత తనిఖీ తర్వాత గ్రేడ్ కనిపిస్తుంది.',

      'status.demo':           'డెమో డేటాసెట్',
      'status.placeholder':    'ML ప్లేస్‌హోల్డర్',
      'status.apiPending':     'API పెండింగ్‌లో ఉంది',
      'status.open':           'ఓపెన్',

      'chat.title':            'KisanLink సహాయకుడు',
      'chat.apiNotice':        'సహాయక బ్యాకెండ్ కనెక్ట్ కాలేదు. ప్రతిస్పందనలు డెమో మాత్రమే.',
      'chat.empty':            'పంట ధరలు లేదా మార్కెట్ గురించి అడగండి.',
      'chat.placeholder':      'మీ పంట లేదా మార్కెట్ గురించి అడగండి...',
      'chat.send':             'పంపండి',
      'chat.voiceStart':       'వాయిస్ ద్వారా అడగండి (మైక్)',
      'chat.voiceListening':   'వింటున్నాను... ఇప్పుడు మాట్లాడండి',
      'chat.voiceStop':        'వినడం ఆపండి',
      'chat.voiceUnsupported': 'ఈ బ్రౌజర్‌లో వాయిస్ ఇన్‌పుట్ సపోర్ట్ లేదు.',
      'chat.speakReply':       'సమాధానం వినండి',
      'chat.q1':               'నేను ఎక్కడ అమ్మాలి?',
      'chat.q2':               'ప్రస్తుత మార్కెట్ ధర ఎంత?',
      'chat.q3':               'ఇప్పుడు అమ్మాలా లేక ఆగాలా?',
      'chat.q4':               'కొనుగోలుదారులను చూపించు',

      'ba.crop':               'పంట',
      'ba.quality':            'గ్రేడ్',
      'ba.location':           'ప్రాంతం',
      'ba.quantity':           'పరిమాణం',
      'ba.marketPrice':        'ప్రస్తుత ధర',
      'ba.forecast':           '7 రోజుల అంచనా',
      'ba.demand':             'కొనుగోలుదారు డిమాండ్',
      'ba.logistics':          'రవాణా ఖర్చు',
      'ba.netRealisation':     'నికర రాబడి',
      'ba.netNote':            'రవాణా మరియు మార్కెట్ ఖర్చులు తీసివేసిన తర్వాత నికర రాబడి.',
      'ba.recLabel':           'సిఫార్సు చేయబడిన చర్య',

      'profile.title':         'రైతు ప్రొఫైల్',
      'profile.contact':       'సంప్రదింపు',
      'profile.language':      'భాష',
      'profile.switch':        'ఖాతా మార్చండి'
    },

    kn: {
      'nav.overview':        'ಅವಲೋಕನ',
      'nav.saleLots':        'ನನ್ನ ಮಾರಾಟ ಲಾಟ್‌ಗಳು',
      'nav.marketIntel':     'ಮಾರುಕಟ್ಟೆ ಮಾಹಿತಿ',
      'nav.recommendation':  'ಶಿಫಾರಸು',
      'nav.buyerMatches':    'ಖರೀದಿದಾರರ ಹೊಂದಾಣಿಕೆ',
      'nav.offers':          'ಸ್ವೀಕರಿಸಿದ ಆಫರ್‌ಗಳು',
      'nav.transactions':    'ವಹಿವಾಟುಗಳು',
      'nav.cropQuality':     'ಬೆಳೆ ಗುಣಮಟ್ಟ ಪರಿಶೀಲನೆ',
      'nav.priceOutlook':    'ಬೆಲೆ ಮುನ್ನೋಟ',
      'nav.bestAction':      'ಉತ್ತಮ ನಿರ್ಧಾರ',
      'topbar.createLot':    '+ ಮಾರಾಟ ಲಾಟ್ ರಚಿಸಿ',
      'topbar.switchBuyer':  'ಖರೀದಿದಾರರ ಪೋರ್ಟಲ್',
      'topbar.home':         'ಮುಖಪುಟ',

      'qa.title':            'ರೈತ ತ್ವರಿತ ಕ್ರಿಯೆಗಳು',
      'qa.sellNow':          'ಈಗಲೇ ಮಾರಿ',
      'qa.wait':             'ಉತ್ತಮ ಬೆಲೆಗಾಗಿ ಕಾಯಿರಿ',
      'qa.compare':          'ಮಾರುಕಟ್ಟೆ ಹೋಲಿಕೆ',
      'qa.checkQuality':     'ಗುಣಮಟ್ಟ ಪರಿಶೀಲಿಸಿ',
      'qa.findBuyers':       'ಖರೀದಿದಾರರನ್ನು ಹುಡುಕಿ',

      'section.bestAction':    'ನಿಮ್ಮ ಬೆಳೆಗೆ ಉತ್ತಮ ನಿರ್ಧಾರ',
      'section.priceOutlook':  'ಬೆಲೆ ಮುನ್ನೋಟ & 7 ದಿನಗಳ ಅಂದಾಜು',
      'section.marketCompare': 'ಹತ್ತಿರದ ಮಾರುಕಟ್ಟೆಗಳನ್ನು ಹೋಲಿಕೆ ಮಾಡಿ',
      'section.buyerMatches':  'ಖರೀದಿದಾರರ ಅವಕಾಶಗಳು',
      'section.notifications': 'ಚಟುವಟಿಕೆ & ಸೂಚನೆಗಳು',
      'section.cropQuality':   'ಬೆಳೆ ಗುಣಮಟ್ಟ ತಪಾಸಣೆ',
      'section.saleLots':      'ಸಕ್ರಿಯ ಮಾರಾಟ ಲಾಟ್‌ಗಳು',

      'action.sellNow':        'ಈಗಲೇ ಮಾರಿ',
      'action.wait':           'ಕಾಯಿರಿ',
      'action.compare':        'ಮಾರುಕಟ್ಟೆ ಹೋಲಿಕೆ',
      'action.analyze':        'ಗುಣಮಟ್ಟ ವಿಶ್ಲೇಷಣೆ',
      'action.viewDetail':     'ವಿವರ ವೀಕ್ಷಿಸಿ',
      'action.makeOffer':      'ಆಫರ್ ಪರಿಶೀಲಿಸಿ',
      'action.takePhoto':      'ಫೋಟೋ ತೆಗೆಯಿರಿ',
      'action.uploadImage':    'ಚಿತ್ರ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',
      'action.capture':        'ಫೋಟೋ ಸೆರೆಹಿಡಿಯಿರಿ',
      'action.retake':         'ಮತ್ತೆ ತೆಗೆಯಿರಿ',
      'action.remove':         'ತೆಗೆದುಹಾಕಿ',
      'action.browse':         'ಫೈಲ್ ಆಯ್ಕೆಮಾಡಿ',
      'action.analyzeAgain':   'ಮತ್ತೆ ವಿಶ್ಲೇಷಿಸಿ',
      'action.applyPipeline':  'ನಿರ್ಧಾರ ಎಂಜಿನ್‌ಗೆ ಅನ್ವಯಿಸಿ',
      'action.getForecast':    'ಮುನ್ನೋಟ ಪಡೆಯಿರಿ',
      'action.fetchMarkets':   'ಮಾರುಕಟ್ಟೆ ಹೋಲಿಕೆ',

      'cqa.guide.title':       'ಉತ್ತಮ ಫಲಿತಾಂಶಕ್ಕಾಗಿ ಫೋಟೋ ಸಲಹೆಗಳು',
      'cqa.guide.g1':          'ನೈಸರ್ಗಿಕ ಬೆಳಕಿನಲ್ಲಿ ಫೋಟೋ ತೆಗೆಯಿರಿ.',
      'cqa.guide.g2':          'ಬೆಳೆಯನ್ನು ಮಧ್ಯದಲ್ಲಿ ಸ್ಪಷ್ಟವಾಗಿ ಇರಿಸಿ.',
      'cqa.guide.g3':          'ಮಸುಕಾದ ಫೋಟೋಗಳನ್ನು ತಪ್ಪಿಸಿ.',
      'cqa.guide.g4':          'ಬೆಳೆಯ ಬಣ್ಣ ಮತ್ತು ಗಾತ್ರ ಸ್ಪಷ್ಟವಾಗಿ ಕಾಣಿಸಲಿ.',

      'cqa.state.notAssessed': 'ಗುಣಮಟ್ಟದ ಫಲಿತಾಂಶ ಇಲ್ಲಿ ಕಾಣಿಸುತ್ತದೆ',
      'cqa.state.notAssessedSub': 'ಫೋಟೋ ಆಯ್ಕೆಮಾಡಿ "ಗುಣಮಟ್ಟ ವಿಶ್ಲೇಷಣೆ" ಕ್ಲಿಕ್ ಮಾಡಿ.',
      'cqa.state.assessing':   'ಗುಣಮಟ್ಟ ವಿಶ್ಲೇಷಣೆ ನಡೆಯುತ್ತಿದೆ...',
      'cqa.state.assessingSub':'ಚಿತ್ರ ಕಳುಹಿಸಲಾಗುತ್ತಿದೆ, ದಯವಿಟ್ಟು ಕಾಯಿರಿ.',
      'cqa.state.gradeLabel':  'ಅಂದಾಜು ಗ್ರೇಡ್',
      'cqa.state.confLabel':   'ವಿಶ್ವಾಸಾರ್ಹತೆ',
      'cqa.state.indicators':  'ಗುಣಮಟ್ಟ ಸೂಚಕಗಳು',
      'cqa.state.placeholder': 'ML ಸಂಪರ್ಕ ಬಾಕಿ ಇದೆ',
      'cqa.state.placeholderMsg': 'ML ಸೇವೆ ಸಂಪರ್ಕಗೊಂಡಾಗ ಫಲಿತಾಂಶ ಕಾಣಿಸುತ್ತದೆ.',
      'cqa.state.gradePending':'ಪರಿಶೀಲನೆಯ ನಂತರ ಗ್ರೇಡ್ ಲಭ್ಯವಾಗುತ್ತದೆ.',

      'status.demo':           'ಡೆಮೊ ಡೇಟಾ',
      'status.placeholder':    'ML ಪ್ಲೇಸ್‌ಹೋಲ್ಡರ್',
      'status.apiPending':     'API ಬಾಕಿ',
      'status.open':           'ತೆರೆದಿದೆ',

      'chat.title':            'KisanLink ಸಹಾಯಕ',
      'chat.apiNotice':        'ಸಹಾಯಕ ಬ್ಯಾಕೆಂಡ್ ಸಂಪರ್ಕಗೊಂಡಿಲ್ಲ. ಉತ್ತರಗಳು ಡೆಮೊ ಮಾತ್ರ.',
      'chat.empty':            'ಬೆಳೆ ಬೆಲೆ ಅಥವಾ ಮಾರುಕಟ್ಟೆ ಬಗ್ಗೆ ಕೇಳಿ.',
      'chat.placeholder':      'ನಿಮ್ಮ ಬೆಳೆ ಅಥವಾ ಮಾರುಕಟ್ಟೆ ಬಗ್ಗೆ ಕೇಳಿ...',
      'chat.send':             'ಕಳುಹಿಸಿ',
      'chat.voiceStart':       'ಧ್ವನಿಯ ಮೂಲಕ ಕೇಳಿ (ಮೈಕ್)',
      'chat.voiceListening':   'ಕೇಳಿಸಿಕೊಳ್ಳುತ್ತಿದ್ದೇನೆ... ಈಗ ಮಾತನಾಡಿ',
      'chat.voiceStop':        'ನಿಲ್ಲಿಸಿ',
      'chat.voiceUnsupported': 'ಈ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಧ್ವನಿ ಇನ್‌ಪುಟ್ ಬೆಂಬಲಿಸುವುದಿಲ್ಲ.',
      'chat.speakReply':       'ಉತ್ತರ ಆಲಿಸಿ',
      'chat.q1':               'ನಾನು ಎಲ್ಲಿ ಮಾರಾಟ ಮಾಡಬೇಕು?',
      'chat.q2':               'ಪ್ರಸ್ತುತ ಮಾರುಕಟ್ಟೆ ದರ ಎಷ್ಟು?',
      'chat.q3':               'ಈಗ ಮಾರಾಟ ಮಾಡಬೇಕೇ ಅಥವಾ ಕಾಯಬೇಕೇ?',
      'chat.q4':               'ಖರೀದಿದಾರರನ್ನು ತೋರಿಸಿ',

      'ba.crop':               'ಬೆಳೆ',
      'ba.quality':            'ಗ್ರೇಡ್',
      'ba.location':           'ಸ್ಥಳ',
      'ba.quantity':           'ಪ್ರಮಾಣ',
      'ba.marketPrice':        'ಪ್ರಸ್ತುತ ಬೆಲೆ',
      'ba.forecast':           '7 ದಿನಗಳ ಮುನ್ನೋಟ',
      'ba.demand':             'ಖರೀದಿದಾರರ ಬೇಡಿಕೆ',
      'ba.logistics':          'ಸಾರಿಗೆ ವೆಚ್ಚ',
      'ba.netRealisation':     'ನಿರೀಕ್ಷಿತ ನಿವ್ವಳ ಲಾಭ',
      'ba.netNote':            'ಸಾರಿಗೆ ವೆಚ್ಚ ಕಳೆದು ನಿವ್ವಳ ಆದಾಯ.',
      'ba.recLabel':           'ಶಿಫಾರಸು ಮಾಡಿದ ಕ್ರಮ',

      'profile.title':         'ರೈತರ ಪ್ರೊಫೈಲ್',
      'profile.contact':       'ಸಂಪರ್ಕ',
      'profile.language':      'ಭಾಷೆ',
      'profile.switch':        'ಖಾತೆ ಬದಲಾಯಿಸಿ'
    },

    ml: {
      'nav.overview':        'അവലോകനം',
      'nav.saleLots':        'എന്റെ വിൽപ്പന ലോട്ടുകൾ',
      'nav.marketIntel':     'വിപണി വിവരങ്ങൾ',
      'nav.recommendation':  'ശുപാർശ',
      'nav.buyerMatches':    'വാങ്ങുന്നവരുടെ പൊരുത്തം',
      'nav.offers':          'ലഭിച്ച ഓഫറുകൾ',
      'nav.transactions':    'ഇടപാടുകൾ',
      'nav.cropQuality':     'വിള ഗുണനിലവാര പരിശോധന',
      'nav.priceOutlook':    'വില വിവരണം',
      'nav.bestAction':      'മികച്ച തീരുമാനം',
      'topbar.createLot':    '+ വിൽപ്പന ലോട്ട് ഉണ്ടാക്കുക',
      'topbar.switchBuyer':  'വാങ്ങുന്നവരുടെ പോർട്ടൽ',
      'topbar.home':         'ഹോം',

      'qa.title':            'കർഷക പെട്ടെന്നുള്ള പ്രവർത്തനങ്ങൾ',
      'qa.sellNow':          'ഇപ്പോൾ വിൽക്കുക',
      'qa.wait':             'നല്ല വിലയ്ക്കായി കാത്തിരിക്കുക',
      'qa.compare':          'വിപണികൾ താരതമ്യം ചെയ്യുക',
      'qa.checkQuality':     'ഗുണനിലവാരം പരിശോധിക്കുക',
      'qa.findBuyers':       'വാങ്ങുന്നവരെ കണ്ടെത്തുക',

      'section.bestAction':    'നിങ്ങളുടെ വിളയ്ക്കുള്ള മികച്ച തീരുമാനം',
      'section.priceOutlook':  'വില വീക്ഷണവും 7 ദിവസത്തെ പ്രവചനവും',
      'section.marketCompare': 'സമീപ വിപണികളുടെ താരതമ്യം',
      'section.buyerMatches':  'വാങ്ങുന്നവരുടെ അവസരങ്ങൾ',
      'section.notifications': 'അറിയിപ്പുകൾ',
      'section.cropQuality':   'വിള ഗുണനിലവാര പരിശോധന',
      'section.saleLots':      'സജീവ വിൽപ്പന ലോട്ടുകൾ',

      'action.sellNow':        'ഇപ്പോൾ വിൽക്കുക',
      'action.wait':           'കാത്തിരിക്കുക',
      'action.compare':        'വിപണി താരതമ്യം',
      'action.analyze':        'ഗുണനിലവാരം വിലയിരുത്തുക',
      'action.viewDetail':     'വിശദാംശങ്ങൾ കാണുക',
      'action.makeOffer':      'ഓഫർ കാണുക',
      'action.takePhoto':      'ഫോട്ടോ എടുക്കുക',
      'action.uploadImage':    'ചിത്രം അപ്‌ലോഡ് ചെയ്യുക',
      'action.capture':        'ചിത്രം പകർത്തുക',
      'action.retake':         'വീണ്ടും എടുക്കുക',
      'action.remove':         'ഒഴിവാക്കുക',
      'action.browse':         'ഫയൽ തിരഞ്ഞെടുക്കുക',
      'action.analyzeAgain':   'വീണ്ടും പരിശോധിക്കുക',
      'action.applyPipeline':  'തീരുമാനത്തിലേക്ക് പ്രയോഗിക്കുക',
      'action.getForecast':    'പ്രവചനം നേടുക',
      'action.fetchMarkets':   'വിപണി താരതമ്യം',

      'cqa.guide.title':       'കൃത്യമായ ഫോട്ടോ നിർദ്ദേശങ്ങൾ',
      'cqa.guide.g1':          'നല്ല വെളിച്ചത്തിൽ ഫോട്ടോ എടുക്കുക.',
      'cqa.guide.g2':          'വിള വ്യക്തമായി മധ്യത്തിൽ വയ്ക്കുക.',
      'cqa.guide.g3':          'വ്യക്തതയില്ലാത്ത ഫോട്ടോകൾ ഒഴിവാക്കുക.',
      'cqa.guide.g4':          'വിളയുടെ നിറവും വലിപ്പവും വ്യക്തമായി കാണിക്കുക.',

      'cqa.state.notAssessed': 'ഗുണനിലവാര ഫലം ഇവിടെ കാണാം',
      'cqa.state.notAssessedSub': 'ഫോട്ടോ എടുത്ത് "ഗുണനിലവാരം വിലയിരുത്തുക" ക്ലിക്ക് ചെയ്യുക.',
      'cqa.state.assessing':   'പരിശോധന പുരോഗമിക്കുന്നു...',
      'cqa.state.assessingSub':'ചിത്രം പരിശോധിക്കുകയാണ്, ദയവായി കാത്തിരിക്കുക.',
      'cqa.state.gradeLabel':  'കണക്കാക്കിയ ഗ്രേഡ്',
      'cqa.state.confLabel':   'കൃത്യത',
      'cqa.state.indicators':  'ഗുണനിലവാര സൂചികകൾ',
      'cqa.state.placeholder': 'ML കണക്ഷൻ കാത്തിരിക്കുന്നു',
      'cqa.state.placeholderMsg': 'സേവനം ലഭ്യമാകുമ്പോൾ ഫലം കാണിക്കും.',
      'cqa.state.gradePending':'പരിശോധനയ്ക്ക് ശേഷം ഗ്രേഡ് ലഭിക്കും.',

      'status.demo':           'ഡെമോ ഡാറ്റ',
      'status.placeholder':    'ML പ്ലേസ്‌ഹോൾഡർ',
      'status.apiPending':     'API കാത്തിരിക്കുന്നു',
      'status.open':           'തുറന്നത്',

      'chat.title':            'KisanLink സഹായി',
      'chat.apiNotice':        'സഹായി ബന്ധിപ്പിച്ചിട്ടില്ല. മറുപടികൾ ഡെമോ മാത്രമാണ്.',
      'chat.empty':            'വിളവിലയോ വിപണിയോ സംബന്ധിച്ച് ചോദിക്കുക.',
      'chat.placeholder':      'നിങ്ങളുടെ വിളയെക്കുറിച്ച് ചോദിക്കുക...',
      'chat.send':             'അയക്കുക',
      'chat.voiceStart':       'ശബ്ദത്തിലൂടെ ചോദിക്കുക (മൈക്ക്)',
      'chat.voiceListening':   'കേൾക്കുന്നു... സംസാരിക്കുക',
      'chat.voiceStop':        'നിർത്തുക',
      'chat.voiceUnsupported': 'ഈ ബ്രൗസറിൽ വോയ്‌സ് ഇൻപുട്ട് ലഭ്യമല്ല.',
      'chat.speakReply':       'ഉത്തരം കേൾക്കുക',
      'chat.q1':               'ഞാൻ എവിടെ വിൽക്കണം?',
      'chat.q2':               'ഇപ്പോഴത്തെ വിപണി വില എത്രയാണ്?',
      'chat.q3':               'ഇപ്പോൾ വിൽക്കണമോ അതോ കാത്തിരിക്കണമോ?',
      'chat.q4':               'വാങ്ങുന്നവരെ കാണിക്കുക',

      'ba.crop':               'വിള',
      'ba.quality':            'ഗ്രേഡ്',
      'ba.location':           'സ്ഥലം',
      'ba.quantity':           'അളവ്',
      'ba.marketPrice':        'നിലവിലെ വില',
      'ba.forecast':           '7 ദിവസത്തെ പ്രവചനം',
      'ba.demand':             'ഡിമാൻഡ്',
      'ba.logistics':          'ഗതാഗത ചിലവ്',
      'ba.netRealisation':     'പ്രതീക്ഷിക്കുന്ന വരുമാനം',
      'ba.netNote':            'ചിലവുകൾ കഴിച്ച് ലഭിക്കുന്ന തുക.',
      'ba.recLabel':           'ശുപാർശ',

      'profile.title':         'കർഷക പ്രൊഫൈൽ',
      'profile.contact':       'ബന്ധപ്പെടുക',
      'profile.language':      'ഭാഷ',
      'profile.switch':        'അക്കൗണ്ട് മാറ്റുക'
    },

    or: {
      'nav.overview':        'ସମୀକ୍ଷା',
      'nav.saleLots':        'ମୋର ବିକ୍ରୟ ଲଟ୍',
      'nav.marketIntel':     'ମଣ୍ଡି ସୂଚନା',
      'nav.recommendation':  'ପରାମର୍ଶ',
      'nav.buyerMatches':    'କ୍ରେତା ମେଳ',
      'nav.offers':          'ପ୍ରାପ୍ତ ଅଫର',
      'nav.transactions':    'କାରବାର',
      'nav.cropQuality':     'ଫସଲ ଗୁଣବତ୍ତା ଯାଞ୍ଚ',
      'nav.priceOutlook':    'ଦର ଦୃଷ୍ଟିକୋଣ',
      'nav.bestAction':      'ସର୍ବୋତ୍ତମ ପଦକ୍ଷେପ',
      'topbar.createLot':    '+ ବିକ୍ରୟ ଲଟ୍ ତିଆରି କରନ୍ତୁ',
      'topbar.switchBuyer':  'କ୍ରେତା ପୋର୍ଟାଲ',
      'topbar.home':         'ମୂଳପୃଷ୍ଠା',

      'qa.title':            'କୃଷକ ତ୍ୱରିତ କାର୍ଯ୍ୟ',
      'qa.sellNow':          'ଏବେ ବିକ୍ରି କରନ୍ତୁ',
      'qa.wait':             'ଭଲ ଦର ପାଇଁ ଅପେକ୍ଷା କରନ୍ତୁ',
      'qa.compare':          'ମଣ୍ଡି ଦର ତୁଳନା କରନ୍ତୁ',
      'qa.checkQuality':     'ଗୁଣବତ୍ତା ଯାଞ୍ଚ କରନ୍ତୁ',
      'qa.findBuyers':       'କ୍ରେତା ଖୋଜନ୍ତୁ',

      'section.bestAction':    'ଆପଣଙ୍କ ଫସଲ ପାଇଁ ସର୍ବୋତ୍ତମ ପଦକ୍ଷେପ',
      'section.priceOutlook':  'ଦର ପୂର୍ବାନୁମାନ ଓ ୭-ଦିନର ଟ୍ରେଣ୍ଡ',
      'section.marketCompare': 'ନିକଟସ୍ଥ ମଣ୍ଡିର ତୁଳନା',
      'section.buyerMatches':  'କ୍ରେତା ସୁଯୋଗ',
      'section.notifications': 'ସୂଚନା ଓ ବିଜ୍ଞପ୍ତି',
      'section.cropQuality':   'ଫସଲ ଗୁଣବତ୍ତା ପରୀକ୍ଷା',
      'section.saleLots':      'ସକ୍ରିୟ ବିକ୍ରୟ ଲଟ୍',

      'action.sellNow':        'ଏବେ ବିକ୍ରି କରନ୍ତୁ',
      'action.wait':           'ଅପେକ୍ଷା କରନ୍ତୁ',
      'action.compare':        'ମଣ୍ଡି ତୁଳନା କରନ୍ତୁ',
      'action.analyze':        'ଗୁଣବତ୍ତା ବିଶ୍ଳେଷଣ',
      'action.viewDetail':     'ବିବରଣୀ ଦେଖନ୍ତୁ',
      'action.makeOffer':      'ଅଫର ଦେଖନ୍ତୁ',
      'action.takePhoto':      'ଫଟୋ ଉଠାନ୍ତୁ',
      'action.uploadImage':    'ଫଟୋ ଅପଲୋଡ କରନ୍ତୁ',
      'action.capture':        'ଫଟୋ ନିଅନ୍ତୁ',
      'action.retake':         'ପୁଣି ଥରେ ନିଅନ୍ତୁ',
      'action.remove':         'ହଟାନ୍ତୁ',
      'action.browse':         'ଫାଇଲ ବାଛନ୍ତୁ',
      'action.analyzeAgain':   'ପୁନଃ ଯାଞ୍ଚ କରନ୍ତୁ',
      'action.applyPipeline':  'ନିଷ୍ପତ୍ତିରେ ଯୋଡ଼ନ୍ତୁ',
      'action.getForecast':    'ପୂର୍ବାନୁମାନ ଦେଖନ୍ତୁ',
      'action.fetchMarkets':   'ମଣ୍ଡି ତୁଳନା',

      'cqa.guide.title':       'ଉତ୍ତମ ଫଳାଫଳ ପାଇଁ ଫଟୋ ନିୟମ',
      'cqa.guide.g1':          'ପ୍ରାକୃତିକ ଆଲୋକରେ ଫଟୋ ଉଠାନ୍ତୁ।',
      'cqa.guide.g2':          'ଫସଲକୁ ସ୍ପଷ୍ଟ ଭାବେ ମଝିରେ ରଖନ୍ତୁ।',
      'cqa.guide.g3':          'ଅସ୍ପଷ୍ଟ ବା ଅନ୍ଧାର ଫଟୋ ଉଠାନ୍ତୁ ନାହିଁ।',
      'cqa.guide.g4':          'ଫସଲର ରଙ୍ଗ ଓ ଆକାର ସ୍ପଷ୍ଟ ଦେଖାଯାଉ।',

      'cqa.state.notAssessed': 'ଗୁଣବତ୍ତା ଫଳାଫଳ ଏଠାରେ ଦେଖାଯିବ',
      'cqa.state.notAssessedSub': 'ଫଟୋ ବାଛି "ଗୁଣବତ୍ତା ବିଶ୍ଳେଷଣ" କ୍ଲିକ୍ କରନ୍ତୁ।',
      'cqa.state.assessing':   'ଗୁଣବତ୍ତା ଯାଞ୍ଚ ଚାଲିଛି...',
      'cqa.state.assessingSub':'ଫଟୋ ପଠାଯାଉଛି, ଦୟାକରି ଅପେକ୍ଷା କରନ୍ତୁ।',
      'cqa.state.gradeLabel':  'ଅନୁମାନିତ ଗ୍ରେଡ୍',
      'cqa.state.confLabel':   'ନିର୍ଭୁଲତା',
      'cqa.state.indicators':  'ଗୁଣବତ୍ତା ସୂଚକ',
      'cqa.state.placeholder': 'ML ସଂଯୋଗ ଅପେକ୍ଷିତ',
      'cqa.state.placeholderMsg': 'ML ସେବା ଯୋଡ଼ି ହେବା ପରେ ଗୁଣବତ୍ତା ଦେଖାଯିବ।',
      'cqa.state.gradePending':'ଯାଞ୍ଚ ପରେ ଗ୍ରେଡ୍ ମିଳିବ।',

      'status.demo':           'ଡେମୋ ତଥ୍ୟ',
      'status.placeholder':    'ML ପ୍ଲେସହୋଲ୍ଡର',
      'status.apiPending':     'API ବାକି',
      'status.open':           'ଖୋଲା ଅଛି',

      'chat.title':            'KisanLink ସହାୟକ',
      'chat.apiNotice':        'ସହାୟକ ଯୋଡ଼ା ଯାଇନାହିଁ। ଉତ୍ତରଗୁଡ଼ିକ ଡେମୋ ମାତ୍ର।',
      'chat.empty':            'ଫସଲ ଦର ବା ମଣ୍ଡି ବିଷୟରେ ପଚାରନ୍ତୁ।',
      'chat.placeholder':      'ଆପଣଙ୍କ ଫସଲ ବା ମଣ୍ଡି ବିଷୟରେ ପଚାରନ୍ତୁ...',
      'chat.send':             'ପଠାନ୍ତୁ',
      'chat.voiceStart':       'ଭଏସ୍ ମାଧ୍ୟମରେ ପଚାରନ୍ତୁ (ମାଇକ୍)',
      'chat.voiceListening':   'ଶୁଣୁଛି... ଏବେ କୁହନ୍ତୁ',
      'chat.voiceStop':        'ବନ୍ଦ କରନ୍ତୁ',
      'chat.voiceUnsupported': 'ଏହି ବ୍ରାଉଜରରେ ଭଏସ୍ ଇନପୁଟ୍ ଉପଲବ୍ଧ ନାହିଁ।',
      'chat.speakReply':       'ଉତ୍ତର ଶୁଣନ୍ତୁ',
      'chat.q1':               'ମୁଁ କେଉଁଠି ବିକ୍ରି କରିବା ଉଚିତ୍?',
      'chat.q2':               'ବର୍ତ୍ତମାନର ମଣ୍ଡି ଦର କେତେ?',
      'chat.q3':               'ଏବେ ବିକ୍ରି କରିବି ନା ଅପେକ୍ଷା କରିବି?',
      'chat.q4':               'କ୍ରେତା ସୁଯୋଗ ଦେଖାନ୍ତୁ',

      'ba.crop':               'ଫସଲ',
      'ba.quality':            'ଗ୍ରେଡ୍',
      'ba.location':           'ସ୍ଥାନ',
      'ba.quantity':           'ପରିମାଣ',
      'ba.marketPrice':        'ଚଳିତ ଦର',
      'ba.forecast':           '୭-ଦିନର ପୂର୍ବାନୁମାନ',
      'ba.demand':             'ଚାହିଦା',
      'ba.logistics':          'ପରିବହନ ଖର୍ଚ୍ଚ',
      'ba.netRealisation':     'ନିଟ୍ ଲାଭ',
      'ba.netNote':            'ପରିବହନ ଓ ମଣ୍ଡି ଖର୍ଚ୍ଚ ବାଦ୍ ଦେବା ପରେ ନିଟ୍ ଆୟ।',
      'ba.recLabel':           'ପରାମର୍ଶିତ ପଦକ୍ଷେପ',

      'profile.title':         'କୃଷକ ପ୍ରୋଫାଇଲ୍',
      'profile.contact':       'ଯୋଗାଯୋଗ',
      'profile.language':      'ଭାଷା',
      'profile.switch':        'ଖାତା ବଦଳାନ୍ତୁ'
    },

    as: {
      'nav.overview':        'সামগ্ৰিক ৰূপৰেখা',
      'nav.saleLots':        'মোৰ বিক্ৰী লট',
      'nav.marketIntel':     'বজাৰ তথ্য',
      'nav.recommendation':  'পৰামৰ্শ',
      'nav.buyerMatches':    'ক্ৰেতাৰ মিল',
      'nav.offers':          'প্ৰাপ্ত অফাৰ',
      'nav.transactions':    'লেনদেন',
      'nav.cropQuality':     'শস্যৰ গুণগত মান পৰীক্ষা',
      'nav.priceOutlook':    'মূল্যৰ দৃষ্টিভংগী',
      'nav.bestAction':      'সৰ্বোত্তম সিদ্ধান্ত',
      'topbar.createLot':    '+ বিক্ৰী লট সৃষ্টি কৰক',
      'topbar.switchBuyer':  'ক্ৰেতা পোৰ্টেল',
      'topbar.home':         'গৃহপৃষ্ঠা',

      'qa.title':            'কৃষকৰ তাৎক্ষণিক পদক্ষেপ',
      'qa.sellNow':          'এতিয়াই বিক্ৰী কৰক',
      'qa.wait':             'ভাল দামৰ বাবে অপেক্ষা কৰক',
      'qa.compare':          'বজাৰ তুলনা কৰক',
      'qa.checkQuality':     'গুণমান পৰীক্ষা কৰক',
      'qa.findBuyers':       'ক্ৰেতা সন্ধান কৰক',

      'section.bestAction':    'আপোনাৰ শস্যৰ বাবে সৰ্বোত্তম পদক্ষেপ',
      'section.priceOutlook':  'মূল্যৰ দৃষ্টিভংগী আৰু ৭ দিনৰ পূৰ্বাভাস',
      'section.marketCompare': 'ওচৰৰ বজাৰসমূহৰ তুলনা',
      'section.buyerMatches':  'ক্ৰেতাৰ সুযোগ',
      'section.notifications': 'জাননী আৰু কাৰ্য্যকলাপ',
      'section.cropQuality':   'শস্যৰ গুণগত মান পৰীক্ষা',
      'section.saleLots':      'সক্ৰিয় বিক্ৰী লট',

      'action.sellNow':        'এতিয়াই বিক্ৰী কৰক',
      'action.wait':           'অপেক্ষা কৰক',
      'action.compare':        'বজাৰ তুলনা',
      'action.analyze':        'গুণমান বিশ্লেষণ',
      'action.viewDetail':     'বিৱৰণ চাওক',
      'action.makeOffer':      'অফাৰ পৰ্যালোচনা',
      'action.takePhoto':      'ফটো তোলক',
      'action.uploadImage':    'ফটো আপলোড কৰক',
      'action.capture':        'ফটো লওক',
      'action.retake':         'পুনৰ লওক',
      'action.remove':         'মচক',
      'action.browse':         'ফাইল বাছক',
      'action.analyzeAgain':   'পুনৰ বিশ্লেষণ',
      'action.applyPipeline':  'সিদ্ধান্তত প্ৰয়োগ কৰক',
      'action.getForecast':    'পূৰ্বাভাস চাওক',
      'action.fetchMarkets':   'বজাৰ তুলনা',

      'cqa.guide.title':       'সঠিক গুণমানৰ বাবে ফটো নিৰ্দেশনা',
      'cqa.guide.g1':          'প্ৰাকৃতিক পোহৰত ফটো তোলক।',
      'cqa.guide.g2':          'শস্যখিনি স্পষ্টকৈ মাজত ৰাখক।',
      'cqa.guide.g3':          'অস্পষ্ট বা অন্ধকাৰ ফটো পৰিহাৰ কৰক।',
      'cqa.guide.g4':          'শস্যৰ ৰং আৰু আকাৰ স্পষ্টকৈ দেখুৱাওক।',

      'cqa.state.notAssessed': 'গুণমানৰ ফলাফল ইয়াত ওলাব',
      'cqa.state.notAssessedSub': 'ফটো নিৰ্বাচন কৰি "গুণমান বিশ্লেষণ"ত ক্লিক কৰক।',
      'cqa.state.assessing':   'গুণমান বিশ্লেষণ চলি আছে...',
      'cqa.state.assessingSub':'ছবি পৰীক্ষা কৰা হৈছে, অনুগ্ৰহ কৰি অপেক্ষা কৰক।',
      'cqa.state.gradeLabel':  'আনুমানিক গ্ৰেড',
      'cqa.state.confLabel':   'নিৰ্ভুলতা',
      'cqa.state.indicators':  'গুণমান সূচক',
      'cqa.state.placeholder': 'ML সংযোগৰ অপেক্ষা',
      'cqa.state.placeholderMsg': 'ML সেৱা সংযোগ হ’লে গুণমান ফলাফল ওলাব।',
      'cqa.state.gradePending':'পৰীক্ষাৰ পাছত গ্ৰেড পোৱা যাব।',

      'status.demo':           'ডেমো তথ্য',
      'status.placeholder':    'ML স্থানধাৰক',
      'status.apiPending':     'API বাকী',
      'status.open':           'মুকলি',

      'chat.title':            'KisanLink সহায়ক',
      'chat.apiNotice':        'সহায়ক বেকএণ্ড সংযোগ হোৱা নাই। উত্তৰসমূহ কেৱল ডেমো।',
      'chat.empty':            'শস্যৰ দাম বা বজাৰ সম্পৰ্কে সোধক।',
      'chat.placeholder':      'আপোনাৰ শস্য বা বজাৰ সম্পৰ্কে সোধক...',
      'chat.send':             'পঠিয়াওক',
      'chat.voiceStart':       'মাত মাতি সোধক (মাইক)',
      'chat.voiceListening':   'শুনি আছো... এতিয়া কওক',
      'chat.voiceStop':        'বন্ধ কৰক',
      'chat.voiceUnsupported': 'এই ব্ৰাউজাৰত ভইচ ইনপুট সমৰ্থিত নহয়।',
      'chat.speakReply':       'উত্তৰ শুনক',
      'chat.q1':               'মই ক’ত বিক্ৰী কৰা উচিত?',
      'chat.q2':               'বৰ্তমান বজাৰ দৰ কিমান?',
      'chat.q3':               'এতিয়া বিক্ৰী কৰিম নে অপেক্ষা কৰিম?',
      'chat.q4':               'ক্ৰেতাৰ তালিকা দেখুৱাওক',

      'ba.crop':               'শস্য',
      'ba.quality':            'গ্ৰেড',
      'ba.location':           'স্থান',
      'ba.quantity':           'পৰিমাণ',
      'ba.marketPrice':        'বৰ্তমান দৰ',
      'ba.forecast':           '৭ দিনৰ পূৰ্বাভাস',
      'ba.demand':             'চাহিদা',
      'ba.logistics':          'পৰিবহন খৰচ',
      'ba.netRealisation':     'প্ৰত্যাশিত নিট লাভ',
      'ba.netNote':            'পৰিবহন খৰচ বাদ দিয়াৰ পাছত প্ৰকৃত লাভ।',
      'ba.recLabel':           'পৰামৰ্শ',

      'profile.title':         'কৃষকৰ প্ৰফাইল',
      'profile.contact':       'যোগাযোগ',
      'profile.language':      'ভাষা',
      'profile.switch':        'একাউণ্ট সলনি কৰক'
    },

    ur: {
      'nav.overview':        'جائزہ',
      'nav.saleLots':        'میری فروخت کے لاٹس',
      'nav.marketIntel':     'مارکیٹ معلومات',
      'nav.recommendation':  'تجویز',
      'nav.buyerMatches':    'خریدار کی مطابقت',
      'nav.offers':          'موصول شدہ پیشکشیں',
      'nav.transactions':    'لین دین',
      'nav.cropQuality':     'فصل کی کوالٹی جانچ',
      'nav.priceOutlook':    'قیمت کا منظرنامہ',
      'nav.bestAction':      'بہترین عمل',
      'topbar.createLot':    '+ فروخت کا لاٹ بنائیں',
      'topbar.switchBuyer':  'خریدار پورٹل پر جائیں',
      'topbar.home':         'ہوم',

      'qa.title':            'کسان کے فوری اقدامات',
      'qa.sellNow':          'ابھی بیچیں',
      'qa.wait':             'بہتر قیمت کا انتظار کریں',
      'qa.compare':          'منڈیوں کا موازنہ کریں',
      'qa.checkQuality':     'کوالٹی چیک کریں',
      'qa.findBuyers':       'خریدار تلاش کریں',

      'section.bestAction':    'آپ کی فصل کے لیے بہترین فیصلہ',
      'section.priceOutlook':  'قیمت کا اندازہ اور 7 دن کی پیشین گوئی',
      'section.marketCompare': 'قریبی منڈیوں کا موازنہ',
      'section.buyerMatches':  'خریدار کے مواقع',
      'section.notifications': 'سرگرمیاں اور اطلاعات',
      'section.cropQuality':   'فصل کی کوالٹی کی جانچ',
      'section.saleLots':      'فعال فروخت لاٹس',

      'action.sellNow':        'ابھی بیچیں',
      'action.wait':           'انتظار کریں',
      'action.compare':        'منڈی کا موازنہ',
      'action.analyze':        'کوالٹی تجزیہ',
      'action.viewDetail':     'تفصیلات دیکھیں',
      'action.makeOffer':      'پیشکش کا جائزہ لیں',
      'action.takePhoto':      'تصویر لیں',
      'action.uploadImage':    'تصویر اپ لوڈ کریں',
      'action.capture':        'تصویر کھینچیں',
      'action.retake':         'دوبارہ لیں',
      'action.remove':         'ہٹائیں',
      'action.browse':         'فائل منتخب کریں',
      'action.analyzeAgain':   'دوبارہ تجزیہ کریں',
      'action.applyPipeline':  'فیصلہ سازی میں شامل کریں',
      'action.getForecast':    'پیشین گوئی حاصل کریں',
      'action.fetchMarkets':   'منڈیوں کا موازنہ',

      'cqa.guide.title':       'بہترین نتائج کے لیے تصویر کے رہنما اصول',
      'cqa.guide.g1':          'قدرتی روشنی میں تصویر لیں۔',
      'cqa.guide.g2':          'فصل کو کیمرے کے درمیان میں واضح رکھیں۔',
      'cqa.guide.g3':          'دھندلی تصویروں سے گریز کریں۔',
      'cqa.guide.g4':          'فصل کی رنگت اور سائز واضح نظر آنا چاہیے۔',

      'cqa.state.notAssessed': 'کوالٹی کا نتیجہ یہاں نظر آئے گا',
      'cqa.state.notAssessedSub': 'تصویر منتخب کریں اور "کوالٹی تجزیہ" پر کلک کریں۔',
      'cqa.state.assessing':   'کوالٹی کا تجزیہ ہو رہا ہے...',
      'cqa.state.assessingSub':'تصویر بھیجی جا رہی ہے، براہ کرم انتظار کریں۔',
      'cqa.state.gradeLabel':  'تخمینی گریڈ',
      'cqa.state.confLabel':   'درستگی',
      'cqa.state.indicators':  'کوالٹی اشارے',
      'cqa.state.placeholder': 'ML سروس کا انتظار',
      'cqa.state.placeholderMsg': 'ML سروس منسلک ہونے پر نتیجہ ظاہر ہوگا۔',
      'cqa.state.gradePending':'جانچ کے بعد گریڈ نظر آئے گا۔',

      'status.demo':           'ڈیمو ڈیٹا سیٹ',
      'status.placeholder':    'ML پلیس ہولڈر',
      'status.apiPending':     'API زیر التواء',
      'status.open':           'کھلا ہے',

      'chat.title':            'KisanLink معاون',
      'chat.apiNotice':        'معاون بیک اینڈ منسلک نہیں ہے۔ جوابات صرف ڈیمو ہیں۔',
      'chat.empty':            'فصل کے ریٹ یا منڈی کے بارے میں پوچھیں۔',
      'chat.placeholder':      'اپنی فصل یا منڈی کے بارے میں پوچھیں...',
      'chat.send':             'بھیجیں',
      'chat.voiceStart':       'بول کر پوچھیں (مائیک)',
      'chat.voiceListening':   'سن رہا ہوں... اب بولیں',
      'chat.voiceStop':        'سننا بند کریں',
      'chat.voiceUnsupported': 'اس براؤزر میں آواز کی سہولت دستیاب نہیں ہے۔',
      'chat.speakReply':       'جواب سنیں',
      'chat.q1':               'مجھے کہاں بیچنا چاہیے؟',
      'chat.q2':               'موجودہ منڈی قیمت کیا ہے؟',
      'chat.q3':               'کیا ابھی بیچوں یا انتظار کروں؟',
      'chat.q4':               'خریداروں کی فہرست دکھائیں',

      'ba.crop':               'فصل',
      'ba.quality':            'گریڈ',
      'ba.location':           'مقام',
      'ba.quantity':           'مقدار',
      'ba.marketPrice':        'موجودہ قیمت',
      'ba.forecast':           '7 دن کی پیشین گوئی',
      'ba.demand':             'ڈیمانڈ',
      'ba.logistics':          'ٹرانسپورٹ خرچہ',
      'ba.netRealisation':     'خالص آمدنی',
      'ba.netNote':            'ٹرانسپورٹ اور منڈی چارجز کے بعد خالص بچت۔',
      'ba.recLabel':           'تجویز کردہ عمل',

      'profile.title':         'کسان پروفائل',
      'profile.contact':       'رابطہ',
      'profile.language':      'زبان',
      'profile.switch':        'اکاؤنٹ تبدیل کریں'
    }
  };

  /* ── Internal Helpers ────────────────────────────────────────────────── */
  function _t(key) {
    var dict = TRANSLATIONS[_locale] || TRANSLATIONS[DEFAULT];
    return dict[key] || (TRANSLATIONS[DEFAULT] && TRANSLATIONS[DEFAULT][key]) || key;
  }

  function _applyToDOM() {
    var els = document.querySelectorAll('[data-i18n]');
    els.forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      var attr = el.getAttribute('data-i18n-attr');
      var text = _t(key);
      if (attr) {
        el.setAttribute(attr, text);
      } else {
        el.textContent = text;
      }
    });

    // Update html lang attribute and RTL if Urdu
    document.documentElement.setAttribute('lang', _locale);
    if (_locale === 'ur') {
      document.documentElement.setAttribute('dir', 'rtl');
    } else {
      document.documentElement.removeAttribute('dir');
    }

    // Sync all language dropdown selectors on page
    var selects = document.querySelectorAll('.kl-lang-select, [data-lang-select]');
    selects.forEach(function (sel) {
      sel.value = _locale;
    });

    // Update active state on any language buttons
    var btns = document.querySelectorAll('[data-lang-btn]');
    btns.forEach(function (btn) {
      var isActive = btn.getAttribute('data-lang-btn') === _locale;
      btn.classList.toggle('lang-btn--active', isActive);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  function _persist(locale) {
    try { localStorage.setItem('kl_locale', locale); } catch (e) {}
  }

  function _load() {
    try { return localStorage.getItem('kl_locale'); } catch (e) { return null; }
  }

  /* ── Public API ──────────────────────────────────────────────────────── */
  return {
    /** Translate key to current locale */
    t: _t,

    /** Get current locale code */
    getLocale: function () { return _locale; },

    /** Get BCP-47 speech language code for active locale (e.g. 'hi-IN') */
    getSpeechLocale: function () {
      return (LOCALES[_locale] && LOCALES[_locale].bcp47) || 'en-IN';
    },

    /** Get supported locales dictionary */
    getLocales: function () { return Object.assign({}, LOCALES); },

    /** Get array of supported codes */
    getSupported: function () { return SUPPORTED.slice(); },

    /**
     * Switch locale and re-apply translations to all data-i18n elements
     * @param {string} locale
     */
    setLocale: function (locale) {
      if (!SUPPORTED.includes(locale)) {
        console.warn('[KL_I18n] Unsupported locale:', locale);
        return;
      }
      _locale = locale;
      _persist(locale);
      _applyToDOM();
      document.dispatchEvent(new CustomEvent('kl:localeChanged', { detail: { locale: locale } }));
      console.info('[KL_I18n] Locale changed to:', locale, '(' + (LOCALES[locale] ? LOCALES[locale].name : locale) + ')');
    },

    /** Initialise */
    init: function () {
      var saved = _load();
      if (saved && SUPPORTED.includes(saved)) {
        _locale = saved;
      }
      _applyToDOM();
    }
  };
})();

/* Boot on DOMContentLoaded */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', KL_I18n.init);
} else {
  KL_I18n.init();
}

window.KL_I18n = KL_I18n;
