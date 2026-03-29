import re
import difflib

# --- Industry Keyword Configuration ---

INDUSTRY_CONFIG = {
    "Automotive & Mobility": {
        "Market Entry, Exit & Expansion": {
            "group1": ["automotive", "vehicle", "mobility", "EV"],
            "group2": ["entered", "entry", "exit", "exited", "launch", "expansion", "market entry", "market exit", "scaling", "shutdown", "closure", "pullback"]
        },
        "Product, Model & Platform Launches": {
            "group1": ["automotive", "vehicle", "mobility", "OEM"],
            "group2": ["launched", "unveiled", "introduced", "new model", "vehicle launch", "platform launch", "product rollout", "variant launched"]
        },
        "Leadership Moves & Organisational Change": {
            "group1": ["automotive", "vehicle", "mobility"],
            "group2": ["appointed", "joins", "resigned", "stepped down", "exited", "leadership change", "management reshuffle", "new CEO", "new head"]
        },
        "Partnerships, Deals & Strategic Tie-Ups": {
            "group1": ["automotive", "vehicle", "mobility", "EV"],
            "group2": ["partnered with", "partnership", "collaboration", "strategic alliance", "joint venture", "acquisition", "acquired", "investment"]
        },
        "Policy, Regulation & Compliance Actions": {
            "group1": ["automotive", "vehicle", "mobility", "EV"],
            "group2": ["announced", "notified", "approved", "regulatory action", "policy update", "guidelines issued", "rules notified", "subsidy", "incentive"]
        },
        "Manufacturing, Capacity & Supply Chain Movement": {
            "group1": ["automotive", "vehicle", "OEM", "mobility"],
            "group2": ["new plant", "factory", "capacity expansion", "production ramp-up", "manufacturing facility", "localisation", "sourcing"]
        },
        "Risk Events, Incidents & Scrutiny": {
            "group1": ["automotive", "vehicle", "mobility"],
            "group2": ["recalled", "recall", "incident", "fire", "safety issue", "regulatory scrutiny", "investigation", "complaint", "penalty"]
        }
    },
    "BFSI": {
        "Market Entry, Exit & Expansion": {
            "group1": ["banking", "fintech", "insurance", "wealth management"],
            "group2": ["entered", "entry", "exit", "exited", "license received", "NBFC registration", "expansion", "market entry", "market exit", "scaling", "shutdown", "closure", "pullback"]
        },
        "Product, App & Platform Launches": {
            "group1": ["banking", "fintech", "insurance", "digital lending"],
            "group2": ["launched", "unveiled", "introduced", "new app", "platform launch", "card launch", "policy rollout", "feature update", "neobank launch"]
        },
        "Leadership Moves & Organisational Change": {
            "group1": ["banking", "fintech", "insurance", "mutual fund"],
            "group2": ["appointed", "joins", "resigned", "stepped down", "exited", "leadership change", "management reshuffle", "new CEO", "MD & CEO", "new head"]
        },
        "Partnerships, Deals & Strategic Tie-Ups": {
            "group1": ["banking", "fintech", "insurance", "digital payments"],
            "group2": ["partnered with", "partnership", "collaboration", "co-lending", "bancassurance", "strategic alliance", "joint venture", "acquisition", "acquired", "investment"]
        },
        "Policy, Regulation & Compliance Actions": {
            "group1": ["banking", "fintech", "insurance", "RBI", "SEBI", "IRDAI"],
            "group2": ["announced", "notified", "approved", "circular issued", "regulatory action", "policy update", "guidelines issued", "rules notified", "compliance mandate"]
        },
        "Funding, Capital Raising & Financial Health": {
            "group1": ["banking", "fintech", "insurance", "startup"],
            "group2": ["Series A", "Series B", "IPO", "funding round", "capital infusion", "fundraise", "debt funding", "profitability", "NPA levels", "quarterly results"]
        },
        "Risk Events, Fraud & Regulatory Scrutiny": {
            "group1": ["banking", "fintech", "insurance", "digital wallet"],
            "group2": ["penalized", "penalty", "data breach", "cyber attack", "regulatory scrutiny", "investigation", "fraud", "licence cancelled", "show cause notice", "complaint"]
        }
    },
    "Education & EdTech": {
        "Market Entry, Exit & Expansion": {
            "group1": ["education", "edtech", "higher ed", "k-12"],
            "group2": ["entered", "entry", "exit", "exited", "new campus", "international center", "expansion", "market entry", "market exit", "scaling", "shutdown", "closure", "pullback"]
        },
        "Course, Curriculum & Platform Launches": {
            "group1": ["education", "edtech", "learning", "skill development"],
            "group2": ["launched", "unveiled", "introduced", "new course", "platform launch", "degree program", "curriculum update", "app launch", "certification"]
        },
        "Leadership Moves & Organisational Change": {
            "group1": ["education", "edtech", "university", "college"],
            "group2": ["appointed", "joins", "resigned", "stepped down", "exited", "leadership change", "new CEO", "Vice Chancellor", "Dean", "new head"]
        },
        "Partnerships, Academic Tie-Ups & M&A": {
            "group1": ["education", "edtech", "learning platform"],
            "group2": ["partnered with", "partnership", "collaboration", "academic alliance", "university tie-up", "industry-academia", "joint venture", "acquisition", "acquired", "investment"]
        },
        "Policy, NEP & Regulatory Actions": {
            "group1": ["education", "edtech", "UGC", "AICTE", "Ministry of Education"],
            "group2": ["announced", "notified", "approved", "NEP guidelines", "regulatory action", "policy update", "guidelines issued", "rules notified", "accreditation", "grading"]
        },
        "Infrastructure, Grants & Funding": {
            "group1": ["education", "edtech", "university", "startup"],
            "group2": ["new campus", "R&D center", "Series A", "funding round", "grant received", "fundraise", "endowment", "capital infusion", "infrastructure project"]
        },
        "Academic Integrity, Scrutiny & Incidents": {
            "group1": ["education", "edtech", "university", "test prep"],
            "group2": ["investigation", "regulatory scrutiny", "penalty", "misleading ads", "paper leak", "legal dispute", "complaint", "student protest", "blacklisted"]
        }
    },
    "IT, Software & Telecom": {
        "Market Entry, Exit & Expansion": {
            "group1": ["telecom", "software", "SaaS", "cloud services", "IT"],
            "group2": ["entered", "entry", "exit", "exited", "new circle", "spectrum bid", "global delivery center", "expansion", "market entry", "market exit", "scaling", "shutdown", "closure", "pullback"]
        },
        "Product, Version & Feature Launches": {
            "group1": ["software", "telecom", "digital platform", "app"],
            "group2": ["launched", "unveiled", "introduced", "v2.0", "new feature", "OS update", "5G rollout", "platform launch", "beta release", "GenAI integration"]
        },
        "Leadership Moves & Organisational Change": {
            "group1": ["IT", "software", "telecom", "tech"],
            "group2": ["appointed", "joins", "resigned", "stepped down", "leadership change", "management reshuffle", "new CEO", "CTO", "CIO", "new head"]
        },
        "Partnerships, Deals & M&A": {
            "group1": ["software", "telecom", "cloud", "IT"],
            "group2": ["partnered with", "partnership", "collaboration", "signed deal", "strategic alliance", "joint venture", "system integrator", "acquisition", "acquired", "investment"]
        },
        "Policy, Spectrum & Regulatory Actions": {
            "group1": ["telecom", "software", "TRAI", "MeitY", "data privacy"],
            "group2": ["announced", "notified", "approved", "spectrum auction", "regulatory action", "policy update", "rules notified", "compliance mandate", "DPDP Act", "licence fee"]
        },
        "Infrastructure, Data Centers & R&D": {
            "group1": ["telecom", "software", "data center", "R&D"],
            "group2": ["new plant", "tower rollout", "fiber deployment", "manufacturing facility", "innovation hub", "chip design", "server farm", "connectivity"]
        },
        "Risk Events, Downtime & Cybersecurity": {
            "group1": ["software", "telecom", "IT", "network"],
            "group2": ["outage", "downtime", "data breach", "cyber attack", "security flaw", "investigation", "vulnerability", "penalty", "service disruption", "malware"]
        }
    },
    "Manufacturing, Power & Mining": {
        "Market Entry, Exit & Expansion": {
            "group1": ["manufacturing", "power", "mining", "electricity", "minerals"],
            "group2": ["entered", "entry", "exit", "exited", "new market", "commercial production", "expansion", "market entry", "market exit", "divestment", "shutdown", "closure"]
        },
        "Plant, Project & Asset Commissioning": {
            "group1": ["factory", "power plant", "mine", "manufacturing unit"],
            "group2": ["commissioned", "inaugurated", "operational", "foundation stone", "project launch", "new facility", "grid connection", "mine opening", "unit synchronized"]
        },
        "Leadership Moves & Industrial Relations": {
            "group1": ["manufacturing", "power", "mining", "industrial"],
            "group2": ["appointed", "joins", "resigned", "stepped down", "leadership change", "management reshuffle", "new CEO", "Plant Head", "Director Operations"]
        },
        "Partnerships, PPA & Strategic Alliances": {
            "group1": ["manufacturing", "power", "mining", "renewable energy"],
            "group2": ["partnered with", "partnership", "collaboration", "signed MOU", "PPA signed", "Power Purchase Agreement", "offtake agreement", "joint venture", "acquisition", "acquired", "investment"]
        },
        "Policy, Environmental & Regulatory Actions": {
            "group1": ["manufacturing", "power", "mining", "Ministry of Coal", "MNRE"],
            "group2": ["environmental clearance", "EC granted", "notified", "approved", "policy update", "guidelines issued", "tariff revision", "auction rules", "subsidy", "PLI scheme"]
        },
        "Capacity, Sourcing & Supply Chain": {
            "group1": ["manufacturing", "power", "mining", "raw material"],
            "group2": ["capacity expansion", "production ramp-up", "sourcing deal", "logistics", "supply chain", "inventory", "raw material cost", "localisation", "vendor base"]
        },
        "Safety, ESG & Operational Risks": {
            "group1": ["manufacturing", "power", "mining", "factory"],
            "group2": ["incident", "accident", "fire", "leak", "safety audit", "environmental violation", "penalty", "strike", "lockout", "regulatory scrutiny", "investigation"]
        }
    },
    "Consumer & Retail": {
        "Market Entry, Exit & Expansion": {
            "group1": ["retail", "FMCG", "consumer goods", "D2C"],
            "group2": ["entered", "entry", "exit", "exited", "new market", "store opening", "flagship launch", "expansion", "market entry", "market exit", "geographic footprint"]
        },
        "Product, Brand & Variant Launches": {
            "group1": ["FMCG", "consumer durables", "electronics", "home care"],
            "group2": ["launched", "unveiled", "introduced", "new brand", "product rollout", "limited edition", "variant launch", "sku expansion", "premiumization", "new collection"]
        },
        "Leadership Moves & Management Changes": {
            "group1": ["retail", "FMCG", "consumer brand"],
            "group2": ["appointed", "joins", "resigned", "stepped down", "leadership change", "management reshuffle", "new CEO", "CMO", "Brand Head", "MD"]
        },
        "Partnerships, Retail Tie-Ups & M&A": {
            "group1": ["FMCG", "retail", "e-commerce", "brand"],
            "group2": ["partnered with", "partnership", "collaboration", "signed deal", "distribution tie-up", "strategic alliance", "joint venture", "acquisition", "acquired", "brand buyout", "investment"]
        },
        "Policy, Taxation & Fiscal Updates": {
            "group1": ["FMCG", "retail", "Consumer Affairs", "FSSAI"],
            "group2": ["GST update", "tax cut", "notified", "approved", "legal metrology", "packaging norms", "FSSAI guidelines", "E-commerce rules", "subsidy", "PLI for white goods"]
        },
        "Supply Chain, Manufacturing & Sourcing": {
            "group1": ["manufacturing", "supply chain", "sourcing", "logistics"],
            "group2": ["new plant", "warehouse launch", "capacity expansion", "production unit", "last-mile delivery", "inventory", "sourcing strategy", "raw material cost", "localisation"]
        },
        "Consumer Sentiments, Risks & Scrutiny": {
            "group1": ["FMCG", "consumer goods", "brand", "retailer"],
            "group2": ["recall", "product defect", "misleading ad", "ASCI", "regulatory scrutiny", "consumer complaint", "boycott", "fine", "penalty", "data breach", "safety issue"]
        }
    },
    "NGO & Development Sector": {
        "Regional Focus, New Projects & Expansion": {
            "group1": ["NGO", "social enterprise", "development sector", "PRADAN"],
            "group2": ["new project", "launched initiative", "expanded to", "program rollout", "village coverage", "district entry", "scaling impact", "project launch", "geographical footprint"]
        },
        "Impact Areas, Livelihoods & Women Empowerment": {
            "group1": ["Livelihoods", "Self Help Groups", "SHG", "Women Collectives"],
            "group2": ["income generation", "smallholder farmers", "rural development", "empowerment", "capacity building", "sustainable farming", "INRM", "Agriculture Production Clusters", "APC"]
        },
        "Leadership, Governance & Founders": {
            "group1": ["NGO", "foundations", "non-profit"],
            "group2": ["appointed", "new CEO", "Executive Director", "joins board", "resigned", "leadership change", "trustee", "Deep Joshi", "founder news", "management update"]
        },
        "Partnerships, CSR & Govt. Collaboration": {
            "group1": ["NGO", "social sector", "developmental project"],
            "group2": ["CSR partnership", "partnered with", "MoU signed", "government collaboration", "multi-stakeholder", "Project LEAP", "donor agreement", "grant received", "strategic alliance"]
        },
        "Policy, Advocacy & Sectoral Guidelines": {
            "group1": ["NGO", "civil society", "FCRA", "NITI Aayog"],
            "group2": ["FCRA renewal", "policy update", "regulatory compliance", "notified", "advocacy", "white paper", "SDG goals", "guidelines issued", "rules notified", "tax exemption"]
        },
        "Awards, Recognition & Impact Reports": {
            "group1": ["NGO", "non-profit", "social impact"],
            "group2": ["Awarded", "Annual Report", "impact assessment", "case study", "recognition", "ranking", "best practices", "success story", "milestone achieved"]
        },
        "Scrutiny, Compliance & Operational Risks": {
            "group1": ["NGO", "charity", "foundation"],
            "group2": ["FCRA cancellation", "regulatory scrutiny", "investigation", "funding audit", "legal dispute", "complaint", "misappropriation", "compliance failure", "penalty"]
        }
    }
}

class HeadlineClassifier:
    def __init__(self, industry="Automotive & Mobility"):
        self.industry = industry
        # Default fallback logic
        if self.industry not in INDUSTRY_CONFIG:
            for key in INDUSTRY_CONFIG.keys():
                if self.industry.lower() in key.lower() or key.lower() in self.industry.lower():
                    self.industry = key
                    break
            if self.industry not in INDUSTRY_CONFIG:
                print(f"Warning: Industry '{industry}' not found. Defaulting to 'Automotive & Mobility'.")
                self.industry = "Automotive & Mobility"
        
        # PRE-COMPILE REGEX patterns for performance
        # Each bucket will have compiled re patterns for group1 and group2
        self.compiled_buckets = {}
        raw_buckets = INDUSTRY_CONFIG[self.industry]
        
        for bucket_name, groups in raw_buckets.items():
            # Create regex pattern: (term1|term2|term3) with case insensitivity
            # re.escape is used to ensure special characters don't break regex
            g1_pattern_str = "|".join(map(re.escape, groups['group1']))
            g2_pattern_str = "|".join(map(re.escape, groups['group2']))
            
            self.compiled_buckets[bucket_name] = {
                'group1': re.compile(f"({g1_pattern_str})", re.IGNORECASE),
                'group2': re.compile(f"({g2_pattern_str})", re.IGNORECASE)
            }

    def classify(self, headline):
        """
        Classifies a single headline into one of the buckets using Fast Regex.
        """
        if not headline or not isinstance(headline, str):
             return {
                "text": str(headline),
                "is_relevant": False,
                "assigned_bucket": "Invalid Input",
                "bucket_id": 0,
                "reasoning": "Empty or invalid text",
                "confidence_score": 0.0
            }

        matched_bucket = None
        matched_reasoning = []
        is_relevant = False
        confidence = 0.0
        bucket_id = 0
        
        current_id = 1
        # Iterate over pre-compiled buckets
        for bucket_name, patterns in self.compiled_buckets.items():
            g1_match = patterns['group1'].search(headline)
            g2_match = patterns['group2'].search(headline)
            
            if g1_match and g2_match:
                matched_bucket = bucket_name
                #Extract the actual found text for reasoning
                g1_found = g1_match.group(1)
                g2_found = g2_match.group(1)
                
                matched_reasoning = [f"Found '{g1_found}' (G1) AND '{g2_found}' (G2)"]
                is_relevant = True
                confidence = 0.95
                bucket_id = current_id
                break 
            
            current_id += 1
            
        if not is_relevant:
            matched_bucket = "Uncategorized"
            matched_reasoning = ["No matching keywords found"]
            confidence = 0.0
            bucket_id = 0

        return {
            "text": headline,
            "is_relevant": is_relevant,
            "assigned_bucket": matched_bucket,
            "bucket_id": bucket_id,
            "reasoning": "; ".join(matched_reasoning),
            "confidence_score": confidence
        }

class Deduplicator:
    def __init__(self, similarity_threshold=0.85):
        self.similarity_threshold = similarity_threshold

    def process(self, headlines):
        """
        Processes a list of headlines and flags duplicates using O(N log N) Sort+Window strategy.
        Much faster than O(N^2) while preserving original order.
        """
        if not headlines:
            return []
            
        total = len(headlines)
        print(f"Starting Fast Deduplication for {total} headlines...")

        # 1. Transform to (index, text) and remove non-strings
        indexed_items = []
        for i, h in enumerate(headlines):
            txt = str(h).strip() if h else ""
            indexed_items.append((i, txt))

        # 2. Sort alphabetically to group potential duplicates
        # We assume duplicates are lexically close (e.g. "Ford Launch..." vs "Ford Launch...!")
        sorted_items = sorted(indexed_items, key=lambda x: x[1].lower())
        
        results_map = {} # Map original_index -> result_dict
        
        # Window size: How far back to check in sorted list?
        # A small window (e.g., 5-10) catches almost all "similar" strings 
        # because sorting puts them right next to each other.
        WINDOW_SIZE = 10 
        
        # Store (text, original_index) of items processed within current window that were deemed 'Masters'
        # Actually, simpler: just look back at raw sorted list items.
        
        for i in range(len(sorted_items)):
            if i % 5000 == 0:
                print(f"Processing... {i}/{total}")

            curr_idx, curr_text = sorted_items[i]
            
            if not curr_text:
                results_map[curr_idx] = {
                    'headline': curr_text, 'is_master': False, 
                    'master_headline': None, 'similarity_score': 0.0
                }
                continue

            is_duplicate = False
            best_master_text = None
            best_score = 0.0
            
            # Check against previous K neighbors in the sorted list
            start_lookback = max(0, i - WINDOW_SIZE)
            
            for j in range(i - 1, start_lookback - 1, -1):
                prev_idx, prev_text = sorted_items[j]
                
                # Compare
                ratio = difflib.SequenceMatcher(None, curr_text.lower(), prev_text.lower()).ratio()
                
                if ratio >= self.similarity_threshold:
                    # Found a match!
                    is_duplicate = True
                    best_score = ratio
                    # The neighbor might itself be a duplicate, but effectively 
                    # we just want to flag this one as "not a unique master".
                    # We can point to the neighbor as the "master" for reference.
                    best_master_text = prev_text
                    break # Found a match, stop looking back
            
            if is_duplicate:
                results_map[curr_idx] = {
                    'headline': curr_text,
                    'is_master': False,
                    'master_headline': best_master_text, 
                    'similarity_score': best_score
                }
            else:
                # No match in window -> New Master
                results_map[curr_idx] = {
                    'headline': curr_text,
                    'is_master': True,
                    'master_headline': curr_text,
                    'similarity_score': 1.0
                }

        # 3. Calculate Duplicacy Counts
        # We group by 'master_headline' to find how many times each story appears
        master_counts = {}
        for res in results_map.values():
            mh = res['master_headline']
            if mh:
                master_counts[mh] = master_counts.get(mh, 0) + 1
        
        # 4. Inject Counts back into results
        for res in results_map.values():
            mh = res['master_headline']
            if mh:
                res['duplicacy_count'] = master_counts[mh]
            else:
                res['duplicacy_count'] = 1

        # 5. Reconstruct list in original order
        final_results = [results_map[i] for i in range(total)]
        
        print("Deduplication Complete.")
        return final_results
