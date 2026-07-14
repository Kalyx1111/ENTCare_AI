"""
ENTCare AI - Production Backend Server v1.0
ENT (Ear, Nose, Throat) & Head-Neck Health Intelligence Platform
Port: 5100
=========================================
DISCLAIMER: All AI output is for research/education only.
Not medical advice. Always consult a qualified ENT specialist
(otolaryngologist). ENT EMERGENCY (severe airway obstruction,
uncontrolled epistaxis, sudden hearing loss, peritonsillar
abscess with drooling/stridor): Call 112 (India) / 999 (UK) /
911 (US) immediately.
"""

import os, sys, json, uuid, time, hashlib, logging, datetime, argparse
from pathlib import Path

try:
    from flask import Flask, request, jsonify, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("[FATAL] Flask not installed. Run REPAIR_AND_RECOVER.bat"); sys.exit(1)

try:
    import requests as req_lib; REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import fitz; FITZ_OK = True
except ImportError:
    FITZ_OK = False

try:
    from PIL import Image; PIL_OK = True
except ImportError:
    PIL_OK = False

sys.path.insert(0, str(Path(__file__).parent / "modules"))
try:
    import ai_providers; AI_PROVIDERS_OK = True
except ImportError:
    AI_PROVIDERS_OK = False

BASE_DIR    = Path(__file__).parent.resolve()
UPLOAD_DIR  = BASE_DIR / "uploads"
LOGS_DIR    = BASE_DIR / "logs"
DATA_DIR    = BASE_DIR / "data"
STATIC_DIR  = BASE_DIR / "static"
REPORTS_DIR = BASE_DIR / "reports_db"

for d in [UPLOAD_DIR, LOGS_DIR, DATA_DIR, STATIC_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── SOFTWARESAFETY: no hardcoded secrets — all keys from env or client-supplied at runtime ──
PORT    = int(os.environ.get("ENTCARE_PORT", 5100))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DEFAULT_PROVIDER_KEYS = ai_providers.get_env_keys() if AI_PROVIDERS_OK else {}
VERSION = "1.0.0"

DISCLAIMER = (
    "WARNING - AI RESEARCH DISCLAIMER: All output is AI-generated from published "
    "otolaryngology literature (AAO-HNS, ENT UK, WHO, NICE, AOI - Association of "
    "Otolaryngologists of India, PubMed). For educational research only. NOT a "
    "substitute for professional ENT examination, diagnosis, or treatment. ALWAYS "
    "consult a qualified ENT specialist (otolaryngologist). ENT EMERGENCY (severe "
    "airway obstruction, stridor, uncontrolled nosebleed, sudden hearing loss, "
    "peritonsillar abscess with drooling): Call 112 (India) / 999 (UK) / 911 (US) "
    "immediately."
)

log_file = LOGS_DIR / f"server_{datetime.date.today()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("ENTCareAI")

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
CORS(app, origins="*")  # local single-user tool; no auth/session/cookie state to protect

_RATE_STORE = {}

def _get_client_id():
    return hashlib.sha256((request.remote_addr or "127.0.0.1").encode()).hexdigest()[:16]

def rate_limit_check():
    """SOFTWARESAFETY: route throttling on all endpoints."""
    cid = _get_client_id(); now = time.time()
    _RATE_STORE.setdefault(cid, [])
    _RATE_STORE[cid] = [t for t in _RATE_STORE[cid] if now - t < 60]
    if len(_RATE_STORE[cid]) >= 30: return False
    _RATE_STORE[cid].append(now); return True

def sanitise_api_key(key):
    """SOFTWARESAFETY: treat all client input as untrusted — validate and strip."""
    if not key or not isinstance(key, str): return ""
    key = key.strip()
    if len(key) > 512: return ""
    s = "".join(c for c in key if 0x21 <= ord(c) <= 0x7E)
    return s if len(s) >= 10 else ""

def validate_provider(p):
    """SOFTWARESAFETY: whitelist validation — reject anything not in the known set."""
    valid = {"anthropic","openai","gemini","grok","deepseek","mistral"}
    return p.lower() if p and p.lower() in valid else "anthropic"

def sanitise_text_field(val, max_len=500):
    """SOFTWARESAFETY: bound and strip all free-text client input before use in prompts/logs."""
    if not val or not isinstance(val, str): return ""
    return val.strip()[:max_len]

# ═══════════════════════════════════════════════════════════════
# ENT / OTOLARYNGOLOGY KNOWLEDGE BASE
# Sources: AAO-HNS Guidelines, ENT UK, WHO, NICE,
#          Association of Otolaryngologists of India (AOI), PubMed
# ═══════════════════════════════════════════════════════════════
KNOWLEDGE = {
    "ear_conditions": {
        "name": "Ear Conditions",
        "otitis_media": "Acute otitis media (AOM): middle ear infection, most common in children. Symptoms: otalgia (ear pain), fever, irritability, reduced hearing, occasionally otorrhoea if tympanic membrane perforates. Otoscopy: bulging, erythematous tympanic membrane, loss of light reflex. Management: analgesia (paracetamol/ibuprofen) first-line; antibiotics (amoxicillin) if severe, bilateral in under 2s, or symptoms persist beyond 3 days per watchful-waiting protocols; most resolve spontaneously. Otitis media with effusion (OME/'glue ear'): fluid in middle ear without acute infection signs, common cause of conductive hearing loss in children, often follows AOM. Watchful waiting for 3 months (most resolve spontaneously); grommets (ventilation tubes) considered for persistent bilateral OME with hearing loss affecting development/education.",
        "otitis_externa": "Inflammation of external ear canal, often bacterial (Pseudomonas, Staphylococcus) or fungal (Aspergillus, Candida). Risk factors: swimming ('swimmer's ear'), cotton bud use, eczema, humid climates (relevant in much of India). Symptoms: ear pain (worse on tragal pressure/pinna movement - key distinguishing sign from otitis media), itching, discharge, canal oedema/erythema. Management: topical antibiotic/steroid drops (e.g., ciprofloxacin/dexamethasone), aural toilet (cleaning debris), keep ear dry, analgesia. Malignant/necrotising otitis externa: rare, serious extension into skull base, occurs mainly in diabetics/immunocompromised - requires urgent ENT referral and prolonged IV antibiotics.",
        "hearing_loss": "Conductive hearing loss: problem in outer/middle ear (wax impaction, otitis media/effusion, otosclerosis, tympanic membrane perforation, ossicular chain disruption). Sensorineural hearing loss (SNHL): cochlear or auditory nerve pathology (presbycusis/age-related, noise-induced, ototoxic drugs - aminoglycosides/cisplatin/loop diuretics, Meniere's disease, acoustic neuroma, congenital). Sudden sensorineural hearing loss (SSNHL): ENT EMERGENCY - unilateral hearing loss over less than 72 hours, requires urgent ENT assessment and audiogram; treatment (oral/intratympanic corticosteroids) most effective if started within 2 weeks of onset - delay significantly worsens recovery prognosis. Noise-induced hearing loss: significant occupational and recreational (personal audio device) concern; prevention (hearing protection) is key as damage is irreversible.",
        "tinnitus_vertigo": "Tinnitus: perception of sound without external source, often associated with hearing loss, noise exposure, or Meniere's disease. Usually benign but pulsatile tinnitus or unilateral tinnitus with asymmetric hearing loss warrants imaging to exclude vascular abnormality or acoustic neuroma. Management: address underlying cause, hearing aids if hearing loss present, tinnitus retraining therapy, sound therapy/masking, CBT for distress. Meniere's disease: recurrent vertigo (attacks lasting 20 minutes to hours) with fluctuating sensorineural hearing loss, tinnitus, and aural fullness - classic tetrad. Management: low-salt diet, betahistine, diuretics; intratympanic steroids or gentamicin for refractory cases; surgery (endolymphatic sac decompression, vestibular nerve section) rarely needed. BPPV (benign paroxysmal positional vertigo): brief vertigo triggered by head position change, due to otoconia displacement into semicircular canals - Dix-Hallpike test for diagnosis, Epley manoeuvre highly effective treatment.",
        "cholesteatoma": "Abnormal skin growth in the middle ear, potentially locally destructive (can erode ossicles, bone, and extend intracranially if untreated). Often follows chronic otitis media/tympanic membrane retraction. Symptoms: chronic foul-smelling otorrhoea, conductive hearing loss, occasionally vertigo or facial weakness if advanced. Management: surgical removal (mastoidectomy) is definitive treatment - cannot be treated with drops/antibiotics alone; regular follow-up needed due to recurrence risk.",
    },
    "nose_sinus_conditions": {
        "name": "Nasal & Sinus Conditions",
        "rhinosinusitis": "Acute rhinosinusitis: inflammation of nose/sinuses lasting under 12 weeks, usually viral (most cases self-limiting within 7-10 days). Bacterial superinfection suggested by symptoms worsening after initial improvement, or persisting beyond 10 days with severe symptoms (high fever, purulent discharge, facial pain). Management: analgesia, nasal saline irrigation, intranasal corticosteroids; antibiotics only if bacterial features present (amoxicillin first-line). Chronic rhinosinusitis (CRS): symptoms for 12+ weeks - nasal obstruction, discharge, facial pain/pressure, reduced smell. CRS with nasal polyps vs without polyps - different underlying pathophysiology and treatment response. Management: intranasal corticosteroids (mainstay), saline irrigation, short courses of oral steroids for polyps, biologics (dupilumab) for severe polyp disease, endoscopic sinus surgery for medical treatment failures.",
        "allergic_rhinitis": "IgE-mediated inflammation from allergen exposure (pollen - seasonal, house dust mite/pet dander - perennial). Symptoms: sneezing, clear rhinorrhoea, nasal itching, congestion, often with allergic conjunctivitis. Significant quality of life and sleep impact; associated with asthma (unified airway concept) - allergic rhinitis is a risk factor for asthma development/poor control. Management: allergen avoidance, intranasal corticosteroids (most effective single therapy), non-sedating antihistamines, combination nasal antihistamine/steroid sprays for inadequate response, allergen immunotherapy for severe/refractory cases with confirmed specific allergen.",
        "nasal_polyps": "Benign swellings of nasal/sinus mucosa, associated with chronic rhinosinusitis, asthma, and aspirin-exacerbated respiratory disease (Samter's triad: asthma, nasal polyps, aspirin/NSAID sensitivity). Symptoms: nasal obstruction, anosmia (loss of smell - often prominent), rhinorrhoea, facial pressure. Management: intranasal/oral corticosteroids first-line, biologics (dupilumab, omalizumab, mepolizumab) for severe eosinophilic disease, functional endoscopic sinus surgery (FESS) for medical treatment failure - polyps frequently recur, so postoperative medical therapy is important.",
        "epistaxis": "Nosebleed - anterior (90%+, from Little's area/Kiesselbach's plexus, usually self-limiting) vs posterior (less common, more severe, higher aspiration/airway risk, often in elderly with hypertension or on anticoagulation). First aid: sit upright leaning slightly forward (not backward - avoids swallowing blood), pinch soft cartilaginous part of nose continuously for 10-15 minutes, ice pack. Management if first aid fails: nasal cautery (silver nitrate) or packing (anterior); posterior bleeds may require balloon catheter tamponade or surgical/endoscopic arterial ligation. Recurrent epistaxis: check for hypertension, anticoagulant use, bleeding disorders, hereditary haemorrhagic telangiectasia; consider nasal dryness/topical trauma as contributing factor. SEVERE/UNCONTROLLED epistaxis with haemodynamic compromise is an EMERGENCY.",
        "septal_deviation_trauma": "Deviated nasal septum: can be congenital or post-traumatic, causes unilateral or bilateral nasal obstruction, may worsen sinus drainage and predispose to sinusitis. Management: conservative for mild symptoms, septoplasty for significant obstruction affecting quality of life. Nasal fracture: common facial trauma, assess for septal haematoma (URGENT - requires immediate drainage to prevent septal necrosis/'saddle nose' deformity and abscess), CSF rhinorrhoea (suggests skull base fracture - urgent neurosurgical/ENT assessment), and cosmetic/functional deformity requiring later manipulation/reduction once swelling settles (typically 1-2 weeks post-injury).",
    },
    "throat_voice_conditions": {
        "name": "Throat & Voice Conditions",
        "pharyngitis_tonsillitis": "Acute pharyngitis/tonsillitis: usually viral, but Group A Streptococcus (GAS) important bacterial cause requiring antibiotics to prevent rheumatic fever/glomerulonephritis (particularly relevant given ongoing rheumatic heart disease burden in India). Centor/FeverPAIN criteria help estimate bacterial likelihood (fever, tonsillar exudate, absence of cough, tender anterior cervical lymphadenopathy). Management: analgesia, adequate hydration; antibiotics (penicillin V/amoxicillin) if high bacterial probability score or confirmed GAS. Recurrent tonsillitis: tonsillectomy considered if meeting frequency criteria (e.g., 7 episodes in 1 year, or 5/year for 2 years, or 3/year for 3 years - variably defined) significantly affecting quality of life.",
        "peritonsillar_abscess": "Quinsy - collection of pus between tonsil capsule and pharyngeal muscles, usually complication of tonsillitis. ENT EMERGENCY. Symptoms: severe unilateral throat pain, trismus (difficulty opening mouth - key distinguishing feature), muffled 'hot potato' voice, uvula deviation away from affected side, drooling, fever. Management: needle aspiration or incision and drainage (urgent), IV antibiotics, analgesia; may need admission. Risk of airway compromise if untreated - urgent ENT assessment mandatory.",
        "laryngitis_voice": "Acute laryngitis: usually viral, causes hoarseness/aphonia, resolves within 1-2 weeks with voice rest and hydration. Chronic hoarseness (over 3 weeks): warrants ENT referral for laryngoscopy to exclude vocal cord pathology (nodules/polyps - often from voice overuse, especially in singers/teachers), vocal cord paralysis (can indicate recurrent laryngeal nerve involvement from thyroid, lung, or oesophageal pathology - important red flag), or laryngeal cancer (especially in smokers - persistent hoarseness in a smoker over 3 weeks needs urgent 2-week-wait referral pathway). Management depends on cause: voice therapy (speech and language therapy) for functional/nodule-related dysphonia, surgery for structural lesions not responding to conservative treatment.",
        "dysphagia": "Difficulty swallowing - oropharyngeal (difficulty initiating swallow, coughing/choking, nasal regurgitation - often neurological e.g., stroke, or structural e.g., pharyngeal pouch) vs oesophageal (sensation of food sticking, may be mechanical - stricture, web, tumour - or motility-related - achalasia). ALARM features requiring urgent 2-week-wait referral for endoscopy: progressive dysphagia, weight loss, odynophagia (painful swallowing), anaemia, particularly in patients over 55 - to exclude oesophageal/head-neck malignancy. Globus pharyngeus (sensation of lump in throat without true dysphagia) is common and usually benign but should not be diagnosed without excluding organic pathology first, especially with any red flag symptoms.",
    },
    "head_neck_conditions": {
        "name": "Head & Neck Conditions",
        "neck_lumps": "Systematic assessment essential given wide differential. Site, size, consistency, mobility, tenderness, duration, associated symptoms all matter. Reactive lymphadenopathy: common, usually from local infection, typically resolves. Persistent lymphadenopathy (over 3-4 weeks), especially firm/hard, non-tender, and progressively enlarging, particularly in adults over 40 or with risk factors (smoking, alcohol, HPV exposure) - warrants urgent 2-week-wait referral to exclude malignancy (lymphoma, metastatic head-neck squamous cell carcinoma, thyroid cancer). Congenital neck lumps: thyroglossal duct cyst (midline, moves with tongue protrusion/swallowing), branchial cyst (lateral, usually presents in young adults). Salivary gland swelling (parotid/submandibular): could be infective (mumps, sialadenitis), obstructive (stone/sialolithiasis - often colicky pain worse with eating), or neoplastic (pleomorphic adenoma most common benign; malignant tumours less common but facial nerve involvement is a red flag for malignancy in parotid masses).",
        "thyroid_nodules": "Very common, majority benign. Assessment: TSH, ultrasound (key features suggesting malignancy risk - irregular margins, microcalcifications, taller-than-wide shape, extrathyroidal extension), fine needle aspiration cytology (FNAC) for indeterminate/suspicious nodules using Bethesda classification to guide management. Red flags for malignancy: rapid growth, hoarseness (recurrent laryngeal nerve involvement), fixed/hard nodule, associated cervical lymphadenopathy, history of radiation exposure, family history of thyroid cancer/MEN syndromes. Papillary thyroid carcinoma is most common thyroid cancer type and generally has excellent prognosis with appropriate surgical management (thyroidectomy) and radioactive iodine ablation where indicated.",
        "head_neck_cancer": "Encompasses cancers of oral cavity, oropharynx, larynx, hypopharynx, nasopharynx, salivary glands, thyroid. Major risk factors: tobacco (smoked and smokeless - particularly relevant given India's very high smokeless tobacco/gutka/paan/areca nut use), alcohol (synergistic with tobacco), HPV (increasingly important for oropharyngeal cancer, particularly in non-smokers, generally better prognosis than HPV-negative disease), EBV (nasopharyngeal carcinoma - particularly relevant in certain populations with specific dietary/genetic factors). RED FLAG symptoms warranting urgent 2-week-wait referral: persistent hoarseness over 3 weeks (especially smokers), unexplained neck lump, non-healing mouth ulcer over 3 weeks, unilateral nasal obstruction with bleeding/discharge, unexplained persistent sore throat/dysphagia/odynophagia, unilateral otalgia with normal otoscopy (referred pain pattern - important and often missed red flag), unilateral serous otitis media in an adult (may indicate nasopharyngeal mass obstructing Eustachian tube). Management: multidisciplinary (surgery, radiotherapy, chemotherapy) depending on site/stage; early detection dramatically improves prognosis.",
    },
    "paediatric_ent": {
        "name": "Paediatric ENT",
        "glue_ear_adenotonsillar": "Otitis media with effusion ('glue ear'): leading cause of acquired hearing loss in children, can affect speech/language development and educational progress if prolonged/bilateral. Watchful waiting typically 3 months given high spontaneous resolution rate; grommet insertion (ventilation tubes) considered if persistent bilateral effusion with hearing loss impacting development. Adenotonsillar hypertrophy: common cause of paediatric snoring, mouth breathing, and obstructive sleep apnoea in children (different presentation from adult OSA - often hyperactivity/behavioural issues rather than daytime sleepiness). Adenotonsillectomy considered for significant OSA, recurrent severe tonsillitis meeting frequency criteria, or significant obstructive symptoms affecting growth/behaviour/quality of life.",
        "foreign_bodies": "Nasal foreign bodies: common in young children, unilateral foul-smelling discharge is classic presentation (should prompt suspicion even without witnessed history) - button batteries are a particular EMERGENCY requiring same-day removal due to rapid tissue necrosis from electrical current/chemical burn. Ear foreign bodies: similarly common, button batteries again urgent, insects can be particularly distressing (consider drowning insect with oil before removal attempt). Airway foreign body: choking, stridor, or sudden onset respiratory distress in a child - EMERGENCY requiring immediate assessment; complete obstruction requires back blows/abdominal thrusts per paediatric BLS protocols; partial obstruction with effective cough should not have blind finger sweeps or aggressive intervention that could convert partial to complete obstruction.",
        "paediatric_hearing_screening": "Newborn hearing screening (otoacoustic emissions/automated auditory brainstem response) important for early detection of congenital hearing loss - early intervention (hearing aids, cochlear implants where appropriate) critical for speech/language development given the critical early developmental window. India: newborn hearing screening coverage variable, greater in urban/tertiary settings; awareness and early referral for suspected hearing loss (not responding to sounds, delayed speech) is important given implications for developmental outcomes.",
    },
    "sleep_disordered_breathing": {
        "name": "Sleep-Disordered Breathing",
        "osa_snoring": "Obstructive sleep apnoea (OSA): repeated upper airway collapse during sleep causing apnoeas/hypopnoeas, oxygen desaturation, and sleep fragmentation. Risk factors: obesity (major factor), male sex, large neck circumference, retrognathia, adenotonsillar hypertrophy (children), nasal obstruction. Symptoms: loud snoring with witnessed apnoeas, excessive daytime sleepiness, morning headaches, poor concentration; associated with hypertension, cardiovascular disease, type 2 diabetes, and increased accident risk (driving/occupational). Diagnosis: polysomnography (sleep study) - apnoea-hypopnoea index (AHI) determines severity (mild/moderate/severe). Management: weight loss, CPAP (continuous positive airway pressure - gold standard for moderate-severe OSA), mandibular advancement devices (mild-moderate OSA or CPAP intolerance), positional therapy, surgery (uvulopalatopharyngoplasty, adenotonsillectomy in children) for selected anatomical causes. Simple snoring without apnoea: less concerning medically but can significantly affect bed partner/relationship quality of life.",
    },
    "audiology_vestibular": {
        "name": "Audiology & Vestibular Testing",
        "hearing_tests": "Pure tone audiometry: gold-standard hearing assessment, measures air and bone conduction thresholds across frequencies to distinguish conductive from sensorineural hearing loss and quantify severity. Tympanometry: assesses middle ear function/mobility of tympanic membrane, useful for detecting effusion, perforation, ossicular pathology. Otoacoustic emissions (OAE): used in newborn screening, assesses cochlear outer hair cell function. Speech audiometry: assesses ability to discriminate speech, relevant for hearing aid candidacy assessment and functional impact evaluation.",
        "vestibular_testing": "Vestibular assessment for dizziness/vertigo: Dix-Hallpike manoeuvre for BPPV diagnosis, videonystagmography (VNG)/electronystagmography for more complex vestibular disorders, caloric testing assesses individual ear vestibular function, vestibular evoked myogenic potentials (VEMP) for saccular/utricular function. Distinguishing peripheral (inner ear/vestibular nerve) from central (brainstem/cerebellar) causes of vertigo is critical - central causes (stroke, particularly posterior circulation) can be life-threatening and require urgent neurological assessment; HINTS examination (head impulse, nystagmus, test of skew) can help differentiate in acute vestibular syndrome when performed by trained clinicians.",
    },
    "ent_emergencies": {
        "name": "ENT Emergencies",
        "airway_emergencies": "Acute airway obstruction: EMERGENCY requiring immediate assessment. Causes: foreign body, epiglottitis, severe angioedema, peritonsillar/parapharyngeal abscess, laryngeal trauma, anaphylaxis. Signs of impending airway compromise: stridor (particularly biphasic - suggests severe obstruction), drooling/inability to swallow secretions, tripod positioning, cyanosis, altered consciousness. Epiglottitis: rare now with Hib vaccination but still occurs (also in adults) - rapid onset sore throat, drooling, muffled voice, fever, tripod positioning; AVOID examining throat/upper airway instrumentation without airway control readily available as this can precipitate complete obstruction - urgent anaesthetic/ENT involvement essential, do not attempt to visualise larynx in emergency department without controlled airway setting.",
        "severe_epistaxis": "Uncontrolled or posterior epistaxis with haemodynamic compromise: EMERGENCY. Signs of significant blood loss: tachycardia, hypotension, pallor, dizziness. Management: resuscitation (IV access, fluids, cross-match if severe), posterior nasal packing or balloon tamponade, urgent ENT involvement for possible arterial ligation or embolisation if bleeding uncontrolled with packing. Particular caution in patients on anticoagulation or with bleeding disorders.",
        "sudden_hearing_loss": "Sudden sensorineural hearing loss (SSNHL): unilateral hearing loss developing over less than 72 hours - ENT EMERGENCY requiring urgent audiogram and assessment. Time-critical: corticosteroid treatment (oral or intratympanic) most effective within the first 2 weeks, ideally started as soon as possible - delayed presentation significantly worsens hearing recovery prognosis. MRI internal auditory meati typically arranged to exclude acoustic neuroma as underlying cause.",
        "facial_trauma_septal_haematoma": "Nasal septal haematoma: collection of blood under septal mucoperichondrium following trauma - URGENT, requires same-day incision and drainage to prevent septal cartilage necrosis (avascular necrosis leads to 'saddle nose' deformity) and abscess formation. Any nasal trauma should be examined for this complication. Facial fractures with CSF leak (clear watery rhinorrhoea/otorrhoea after trauma, may test positive for beta-2 transferrin): suggests skull base fracture, requires urgent neurosurgical and ENT assessment, risk of ascending meningitis.",
        "caustic_ingestion_button_battery": "Button battery ingestion/insertion (nose, ear, or swallowed): PAEDIATRIC EMERGENCY requiring same-day removal - causes rapid tissue necrosis through electrical current generation and alkaline chemical burns, can cause perforation/fistula formation within hours. Any suspected button battery exposure requires immediate same-day ENT/emergency assessment regardless of symptoms - do not wait for symptoms to develop.",
    },
    "india_ent": {
        "name": "ENT Care in India",
        "burden_epidemiology": "Chronic suppurative otitis media (CSOM) remains a significant public health burden in India, particularly in lower socioeconomic and rural populations, with higher prevalence linked to overcrowding, malnutrition, and limited access to early ENT care for acute otitis media - untreated/recurrent infections leading to chronic perforation and discharge. Noise-induced hearing loss is a growing occupational health concern given industrial growth, alongside high rates of personal audio device use among younger populations without adequate hearing protection awareness. Nasopharyngeal carcinoma shows notable regional variation, with certain dietary factors (salted fish, preserved foods) and EBV association relevant in some Indian populations, though less common than in Southeast Asian/Chinese populations. Head and neck cancers (particularly oral cavity) represent a very significant cancer burden in India, strongly linked to smokeless tobacco, gutka, paan (betel quid), and areca nut use - among the highest global rates of oral cancer.",
        "treatment_access": "AOI (Association of Otolaryngologists of India) provides national ENT clinical guidance and continuing education. Significant tertiary ENT care available in major cities (AIIMS, other government medical colleges, private hospitals) offering cochlear implantation, skull base surgery, and advanced head-neck oncological surgery comparable to international standards. Rural-urban disparity persists for basic ENT care access, hearing aid provision, and early intervention for paediatric hearing loss. National Programme for Prevention and Control of Deafness (NPPCD) aims to improve early identification and rehabilitation of hearing impairment, including newborn hearing screening initiatives and subsidised hearing aid provision through government schemes. PM-JAY (Ayushman Bharat) provides insurance coverage for major ENT surgical procedures for eligible economically disadvantaged families.",
        "tobacco_oral_cancer_screening": "Given the very high burden of tobacco/areca-nut related oral and oropharyngeal cancers in India, opportunistic oral cavity screening by trained health workers (visual inspection) has shown benefit in reducing mortality from oral cancer in high-risk populations in community-based studies (notably in Kerala). Tobacco cessation counselling integrated into ENT consultations is an important prevention opportunity given the direct causal link to laryngeal, oral, and oropharyngeal cancers. Any non-healing mouth ulcer, white/red patch (leukoplakia/erythroplakia), or persistent hoarseness in a tobacco user should prompt urgent ENT/oral surgery referral.",
    },
}

def save_knowledge():
    with open(DATA_DIR / "ent_knowledge.json", "w", encoding="utf-8") as f:
        json.dump(KNOWLEDGE, f, indent=2, ensure_ascii=False)

def load_sessions():
    sf = DATA_DIR / "sessions.json"
    if sf.exists():
        with open(sf) as f: return json.load(f)
    return {}

def save_session(sid, data):
    sessions = load_sessions()
    sessions[sid] = {**data, "updated": datetime.datetime.now().isoformat()}
    with open(DATA_DIR / "sessions.json", "w") as f: json.dump(sessions, f, indent=2)

def is_online():
    if not REQUESTS_OK: return False
    try: req_lib.get("https://8.8.8.8", timeout=3); return True
    except: return False

def extract_pdf_text(filepath):
    if not FITZ_OK: return "[PDF extraction unavailable]"
    try:
        doc = fitz.open(str(filepath))
        text = "".join(page.get_text() for page in doc)
        doc.close(); return text[:8000]
    except Exception:
        # SOFTWARESAFETY: never leak internal exception/stack trace details to caller
        return "[PDF extraction error]"

DEFAULT_SYSTEM = (
    "You are ENTCare AI, an expert ENT (otolaryngology) health research assistant. "
    "Help patients understand ear, nose, throat, and head-neck conditions from "
    "published otolaryngology literature. "
    "ALWAYS start with a brief AI research disclaimer. "
    "Reference AAO-HNS, ENT UK, WHO, NICE, AOI (Association of Otolaryngologists "
    "of India) guidelines. ALWAYS end reminding them to consult a qualified ENT "
    "specialist. For ENT emergencies (airway obstruction, uncontrolled epistaxis, "
    "sudden hearing loss, peritonsillar abscess, button battery exposure): advise "
    "immediate 112/999/911 or A&E attendance. For Indian patients: reference AOI "
    "guidance, note high smokeless tobacco-related oral/laryngeal cancer burden, "
    "CSOM burden, and NPPCD/PM-JAY where relevant."
)

def call_ai(prompt, system_prompt=None, max_tokens=2500, provider=None, api_key=None):
    if not AI_PROVIDERS_OK: return None, "ai_providers_missing"
    provider = validate_provider(provider)
    effective_key = (sanitise_api_key(api_key) or
                     DEFAULT_PROVIDER_KEYS.get(provider, "") or
                     (API_KEY if provider == "anthropic" else ""))
    if not effective_key or not REQUESTS_OK or not is_online():
        return None, "offline_or_no_key"
    text, mode = ai_providers.call_ai(
        provider, effective_key, prompt, system_prompt or DEFAULT_SYSTEM, max_tokens
    )
    if text is None:
        log.error(f"{provider} API error: {mode}")
        return None, mode
    return text, "live_ai"

def build_offline_response(topic, patient_info=None):
    topic_l = topic.lower()
    kb_key = next(
        (k for k in KNOWLEDGE
         if k.replace("_", " ") in topic_l or topic_l in k.replace("_", " ")
         or any(w in topic_l for w in k.split("_"))),
        None
    )
    lines = [
        "# ENTCare AI Research Report",
        f"**Topic:** {topic}",
        "**Mode:** Offline Research (Embedded ENT Knowledge Base)",
        "",
        "> DISCLAIMER: AI-generated educational information. NOT medical advice. "
        "ALWAYS consult a qualified ENT specialist. "
        "ENT EMERGENCY: Call 112 (India) / 999 (UK) / 911 (US).",
        "", "---", ""
    ]
    if kb_key:
        kb = KNOWLEDGE[kb_key]
        lines.append(f"## {kb.get('name', topic)}\n")
        for field, value in kb.items():
            if field == "name": continue
            if isinstance(value, str):
                lines += [f"**{field.replace('_', ' ').title()}:** {value}", ""]
    else:
        lines += [f"## Research Overview: {topic}", "",
                  f"Enable live AI in Settings for detailed research on {topic}.", ""]
    lines += [
        "---",
        "## India ENT Resources",
        "- AOI: Association of Otolaryngologists of India (aoi-nhq.org)",
        "- AIIMS ENT: aiims.edu",
        "- NPPCD: National Programme for Prevention and Control of Deafness",
        "- PM-JAY: ENT surgical procedure insurance coverage",
        "- Emergency: 112",
        "",
        f"WARNING - {DISCLAIMER}"
    ]
    return "\n".join(lines)

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(STATIC_DIR), filename)

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": VERSION,
                    "online": is_online(), "pdf_extract": FITZ_OK,
                    "timestamp": datetime.datetime.now().isoformat()})

@app.route("/api/upload", methods=["POST"])
def upload():
    if "files" not in request.files: return jsonify({"error": "No files"}), 400
    session_id = request.form.get("session_id") or str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id; session_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for f in request.files.getlist("files"):
        if not f.filename: continue
        ext = Path(f.filename).suffix.lower()
        # SOFTWARESAFETY: never trust client filename — generate opaque server-side name
        safe = f"{uuid.uuid4().hex}{ext}"; dest = session_dir / safe; f.save(str(dest))
        extracted = extract_pdf_text(dest) if ext == ".pdf" else ""
        results.append({"original": f.filename, "saved": safe,
                        "type": "pdf" if ext == ".pdf" else ("image" if ext in [".jpg",".jpeg",".png"] else "text"),
                        "size_kb": round(dest.stat().st_size/1024, 1), "has_content": bool(extracted)})
    existing = load_sessions().get(session_id, {})
    save_session(session_id, {"session_id": session_id, "files": existing.get("files",[]) + results})
    return jsonify({"success": True, "session_id": session_id,
                    "uploaded": len(results), "files": results, "disclaimer": DISCLAIMER})

@app.route("/api/analyse", methods=["POST"])
def analyse():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    topic = sanitise_text_field(data.get("topic", "General ENT"), 200)
    condition = sanitise_text_field(data.get("condition", ""), 200)
    patient_info = data.get("patient_info", {}) if isinstance(data.get("patient_info"), dict) else {}
    provider = validate_provider(data.get("provider", "anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    prompt = (
        f"ENT Research Request: {topic} / {condition}\n"
        f"Patient: Age {sanitise_text_field(str(patient_info.get('age','NR')),10)}, "
        f"Symptoms: {sanitise_text_field(str(patient_info.get('symptoms','NR')),300)}, "
        f"Duration: {sanitise_text_field(str(patient_info.get('duration','NR')),100)}, "
        f"Affected side: {sanitise_text_field(str(patient_info.get('side','NR')),50)}\n"
        f"Medications/History: {sanitise_text_field(str(patient_info.get('history','none')),300)}\n"
        "Cover: clinical overview, differential diagnosis, investigations, "
        "evidence-based treatment options, red flags/warning signs, "
        "India-specific context (AOI, tobacco-related risk), "
        "questions to ask the ENT specialist. Reference AAO-HNS, ENT UK, NICE, AOI."
    )
    result, mode = (call_ai(prompt, provider=provider, api_key=effective_key)
                    if (effective_key and is_online()) else (None,"offline"))
    if not result: result = build_offline_response(topic, patient_info); mode = "offline"
    return jsonify({"success": True, "mode": mode, "analysis": result,
                    "topic": topic, "disclaimer": DISCLAIMER,
                    "timestamp": datetime.datetime.now().isoformat()})

@app.route("/api/condition/<condition_name>")
def condition_detail(condition_name):
    cn = sanitise_text_field(condition_name, 100).lower().replace("-","_").replace(" ","_")
    if cn in KNOWLEDGE:
        return jsonify({"success": True, "mode": "offline_kb",
                        "condition": KNOWLEDGE[cn], "disclaimer": DISCLAIMER})
    provider = validate_provider(request.args.get("provider","anthropic"))
    effective_key = (sanitise_api_key(request.args.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    safe_name = sanitise_text_field(condition_name, 100)
    prompt = (f"Comprehensive ENT research on {safe_name}: "
              "definition, prevalence, pathophysiology, clinical features, diagnosis, "
              "evidence-based management, prognosis. Reference AAO-HNS, ENT UK, NICE, AOI.")
    result, mode = call_ai(prompt, provider=provider, api_key=effective_key)
    if not result: result = build_offline_response(safe_name); mode = "offline"
    return jsonify({"success": True, "mode": mode, "content": result, "disclaimer": DISCLAIMER})

@app.route("/api/ent/assess", methods=["POST"])
def assess_ent():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    symptom = sanitise_text_field(data.get("symptom",""), 300)
    duration = sanitise_text_field(data.get("duration",""), 100)
    age = sanitise_text_field(str(data.get("age","")), 10)
    side = sanitise_text_field(data.get("side",""), 50)
    history = sanitise_text_field(data.get("history",""), 300)
    provider = validate_provider(data.get("provider","anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    if not symptom:
        return jsonify({"error": "Symptom field is required"}), 400
    prompt = (
        f"ENT Assessment Research:\n"
        f"Chief Symptom: {symptom}\nDuration: {duration}\n"
        f"Age: {age}\nAffected Side: {side}\nHistory: {history}\n"
        "Provide: possible causes (most likely to least likely), "
        "urgency of assessment needed, red flags requiring emergency/urgent care, "
        "what the ENT specialist will likely do, questions to ask. "
        "This is educational research — must consult ENT specialist for actual diagnosis."
    )
    result, mode = call_ai(prompt, provider=provider, api_key=effective_key)
    if not result:
        result = (f"ENT assessment research for: {symptom}. "
                  "Enable live AI in Settings for personalised research. "
                  "For any concerning ENT symptom, see your ENT specialist promptly. "
                  "For emergencies (airway obstruction, uncontrolled nosebleed, sudden "
                  "hearing loss): 112/999/911.")
        mode = "offline"
    return jsonify({"success": True, "mode": mode, "content": result, "disclaimer": DISCLAIMER})

@app.route("/api/chat/send", methods=["POST"])
def chat_send():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    message = sanitise_text_field(data.get("message",""), 1000)
    if not message: return jsonify({"error": "Empty message"}), 400
    provider = validate_provider(data.get("provider","anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    result = None
    if data.get("request_ai") and is_online() and effective_key:
        result, _ = call_ai(
            f"ENT patient question: '{message}'. "
            "3-4 paragraphs, compassionate and evidence-based. "
            "Include India-specific guidance where relevant. "
            "End with ENT specialist consultation reminder. "
            "For emergencies (airway obstruction, uncontrolled epistaxis, sudden "
            "hearing loss, peritonsillar abscess): 112/999/911 immediately.",
            max_tokens=800, provider=provider, api_key=effective_key)
    return jsonify({"success": True, "ai_response": result,
                    "disclaimer": "Not medical advice. Consult your ENT specialist."})

@app.route("/api/report/generate", methods=["POST"])
def generate_report():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    topic = sanitise_text_field(data.get("topic","General ENT"), 200)
    patient = data.get("patient_info", {}) if isinstance(data.get("patient_info"), dict) else {}
    provider = validate_provider(data.get("provider","anthropic"))
    effective_key = (sanitise_api_key(data.get("api_key","")) or
                     DEFAULT_PROVIDER_KEYS.get(provider,"") or
                     (API_KEY if provider=="anthropic" else ""))
    content = build_offline_response(topic, patient)
    if effective_key and is_online():
        ai_content, _ = call_ai(
            f"Generate comprehensive ENT research report for: {topic}. "
            f"Patient: {patient}. Cover diagnosis, treatment options, follow-up, prevention.",
            max_tokens=3500, provider=provider, api_key=effective_key)
        if ai_content: content = ai_content
    # SOFTWARESAFETY: opaque, non-sequential identifier — not a predictable/enumerable integer ID
    report_id = f"report_{uuid.uuid4().hex}"
    report = {"report_id": report_id, "generated": datetime.datetime.now().isoformat(),
              "topic": topic, "patient": patient, "content": content, "disclaimer": DISCLAIMER}
    with open(REPORTS_DIR / f"{report_id}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return jsonify(report)

@app.route("/api/resolve", methods=["POST"])
def resolve_multi_ai():
    data = request.json or {}
    if not rate_limit_check(): return jsonify({"error": "Rate limit exceeded"}), 429
    prompt = sanitise_text_field(data.get("prompt",""), 4000)
    if not prompt: return jsonify({"error": "No prompt provided"}), 400
    pairs_raw = data.get("providers",[])
    if not isinstance(pairs_raw, list) or len(pairs_raw) < 1:
        return jsonify({"error": "No providers specified"}), 400
    if not AI_PROVIDERS_OK: return jsonify({"error": "ai_providers module not available"}), 500
    pairs = []
    for p in pairs_raw[:6]:
        if not isinstance(p, dict): continue
        pid = validate_provider(p.get("provider",""))
        key = sanitise_api_key(p.get("key",""))
        if pid and key: pairs.append((pid, key))
    if not pairs: return jsonify({"error": "No valid provider+key pairs"}), 400
    results = ai_providers.call_multi_ai(pairs, prompt, DEFAULT_SYSTEM, 1500)
    successes = [r for r in results if r.get("success") and r.get("text")]
    synthesis = None
    if len(successes) >= 2:
        synth_parts = [f"=== {r.get('label',r.get('provider','AI'))} ===\n{(r.get('text') or '')[:1200]}"
                       for r in successes]
        synth_prompt = (
            "You are an ENT research synthesis engine. Multiple AI systems "
            "answered the same question. Question: " + prompt + "\n\n" +
            "\n\n".join(synth_parts) + "\n\n"
            "Synthesise the best, most complete, evidence-based research answer. "
            "Note any disagreements. Lead with the most clinically important finding. "
            "Remind that this is research only — consult a qualified ENT specialist."
        )
        synth_key = next((k for pr,k in pairs if pr==successes[0]["provider"]), None)
        if synth_key:
            synth_text, _ = ai_providers.call_ai(
                successes[0]["provider"], synth_key, synth_prompt,
                "You are an ENT research synthesis assistant.", 2000)
            synthesis = synth_text
    return jsonify({"success": True, "responses": results,
                    "synthesis": synthesis, "disclaimer": DISCLAIMER})

@app.route("/api/providers")
def list_providers():
    if not AI_PROVIDERS_OK: return jsonify({"providers": [], "error": "ai_providers module not available"})
    return jsonify({"providers": [
        {"id":k,"label":v["label"],"default_model":v["default_model"],
         "key_prefix":v["key_prefix"],"get_key_url":v["get_key_url"],
         "server_default_configured":bool(DEFAULT_PROVIDER_KEYS.get(k))}
        for k,v in ai_providers.PROVIDERS.items()], "online": is_online()})

@app.route("/api/status")
def status():
    any_key = bool(API_KEY) or any(DEFAULT_PROVIDER_KEYS.values())
    return jsonify({"server":"running","version":VERSION,"online":is_online(),
                    "mode":"live_ai" if (any_key and is_online()) else "offline_research",
                    "capabilities":{"pdf":FITZ_OK,"images":PIL_OK,
                                    "live_ai":bool(any_key and is_online()),
                                    "offline":True,"multi_provider":AI_PROVIDERS_OK,
                                    "rate_limiting":True,"aes256_frontend":True,
                                    "ambiguity_resolver":True},
                    "knowledge_base":list(KNOWLEDGE.keys()),
                    "providers":list(ai_providers.PROVIDERS.keys()) if AI_PROVIDERS_OK else [],
                    "disclaimer":DISCLAIMER})

# SOFTWARESAFETY: opaque fault management — never leak stack traces or internals to client
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(e):
    err_ref = uuid.uuid4().hex[:12]
    log.error(f"[{err_ref}] Internal server error: {e}")
    return jsonify({"error": "Internal server error", "reference": err_ref}), 500

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    save_knowledge()
    log.info("="*60)
    log.info(f"  ENTCare AI Server v{VERSION} - Port {args.port}")
    log.info(f"  Online: {is_online()}")
    log.info(f"  URL: http://localhost:{args.port}")
    log.info(f"  Providers: {list(ai_providers.PROVIDERS.keys()) if AI_PROVIDERS_OK else 'N/A'}")
    log.info("="*60)
    app.run(host="0.0.0.0", port=args.port, debug=False, threaded=True, use_reloader=False)
