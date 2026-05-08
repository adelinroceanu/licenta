"""
Generator de date sintetice pentru detectorul EDoS.
Simulează trafic legitim și trafic atacator, apoi extrage features pe ferestre de 30s.

Rulează: python training/generate_edos_data.py
Ieșire: training/data/edos_features.csv
"""
import numpy as np
import pandas as pd
from collections import Counter
import math

# ---------- Parametri ----------
WINDOW_SECONDS = 30
LEGIT_HOURS = 4   # 4 ore trafic legitim
ATTACK_HOURS = 2  # 2 ore trafic atacator

# Pool-uri de IP-uri
LEGIT_IPS = [f"10.0.{i}.{j}" for i in range(1, 5) for j in range(1, 30)]  # ~120 IP-uri
ATTACK_IP_POOL = [f"172.16.{i}.{j}" for i in range(0, 8) for j in range(0, 25)]  # 200 IP-uri spoofate

MSG_TYPES = ['Registration', 'PDU_Establishment', 'PDU_Release', 'Deregistration']

# ---------- Generare evenimente individuale ----------
def generate_legit_window(window_idx):
    """Generează evenimente pentru un interval de 30s de trafic legitim."""
    events = []

    # Variație diurnă: orele de vârf au rate de 2-3x mai mari
    # Simulăm asta amestecând ferestre liniștite cu ferestre de vârf
    is_peak = np.random.random() < 0.30  # 30% din ferestre sunt de vârf

    if is_peak:
        n_events = np.random.randint(60, 120)  # vârf
    else:
        n_events = np.random.randint(20, 60)   # liniștit

    for _ in range(n_events):
        ip = np.random.choice(LEGIT_IPS)
        msg = np.random.choice(MSG_TYPES, p=[0.30, 0.35, 0.30, 0.05])
        duration = np.random.exponential(scale=120) if msg == 'PDU_Release' else None
        events.append({'ip': ip, 'msg_type': msg, 'duration': duration})

    return events

def generate_attack_window(window_idx):
    """
    Generează evenimente pentru un interval de 30s sub atac EDoS.
    Atacatorii reali încearcă să se camufleze:
    - rate doar puțin peste normal
    - mai puține IP-uri unice (ca să nu fie detectați prea ușor)
    - distribuție de mesaje mai aproape de cea legitimă
    """
    events = []

    # Trafic legitim concomitent (ușor mai mult ca să sune ca o oră de vârf)
    n_legit = np.random.randint(40, 80)
    for _ in range(n_legit):
        ip = np.random.choice(LEGIT_IPS)
        msg = np.random.choice(MSG_TYPES, p=[0.30, 0.35, 0.30, 0.05])
        duration = np.random.exponential(scale=120) if msg == 'PDU_Release' else None
        events.append({'ip': ip, 'msg_type': msg, 'duration': duration})

    # Trafic atacator: rate mai modest, ca să simuleze atac „low and slow"
    # Intensitate variabilă: 30-80 cereri în plus față de legitim
    n_attack = np.random.randint(30, 80)

    # Atacatorul folosește doar un subset din pool, rotind între ferestre
    attack_subset_size = np.random.randint(40, 100)
    attack_subset = np.random.choice(ATTACK_IP_POOL, size=attack_subset_size, replace=False)

    for _ in range(n_attack):
        ip = np.random.choice(attack_subset)
        # Distribuție mai aproape de cea legitimă, dar cu bias pe Registration
        msg = np.random.choice(MSG_TYPES, p=[0.55, 0.25, 0.15, 0.05])
        duration = np.random.exponential(scale=120) if msg == 'PDU_Release' else None
        events.append({'ip': ip, 'msg_type': msg, 'duration': duration})

    return events

# ---------- Extragere features ----------
def shannon_entropy(values):
    """Entropia Shannon a unei distribuții discrete."""
    if not values:
        return 0.0
    counts = Counter(values)
    total = sum(counts.values())
    probabilities = [c / total for c in counts.values()]
    return -sum(p * math.log2(p) for p in probabilities if p > 0)

def extract_features(events):
    """Extrage features pe o fereastră (listă de evenimente)."""
    if not events:
        return None

    ips = [e['ip'] for e in events]
    msgs = [e['msg_type'] for e in events]

    durations = [e['duration'] for e in events if e['duration'] is not None]

    return {
        'req_rate': len(events) / WINDOW_SECONDS,
        'unique_sources': len(set(ips)),
        'ip_entropy': shannon_entropy(ips),
        'reg_ratio': msgs.count('Registration') / len(msgs),
        'pdu_setup_ratio': msgs.count('PDU_Establishment') / len(msgs),
        'pdu_release_ratio': msgs.count('PDU_Release') / len(msgs),
        'mean_session_duration': np.mean(durations) if durations else 0.0,
    }

# ---------- Generare dataset ----------
print("=== Generare ferestre de trafic legitim ===")
legit_windows = LEGIT_HOURS * 3600 // WINDOW_SECONDS  # 4 ore = 480 ferestre
legit_features = []
for i in range(legit_windows):
    events = generate_legit_window(i)
    features = extract_features(events)
    if features:
        features['label'] = 0  # legitim
        legit_features.append(features)

print(f"Generate {len(legit_features)} ferestre legitime")

print("\n=== Generare ferestre de atac EDoS ===")
attack_windows = ATTACK_HOURS * 3600 // WINDOW_SECONDS  # 2 ore = 240 ferestre
attack_features = []
for i in range(attack_windows):
    events = generate_attack_window(i)
    features = extract_features(events)
    if features:
        features['label'] = 1  # atac
        attack_features.append(features)

print(f"Generate {len(attack_features)} ferestre atacator")

# ---------- Salvare ----------
all_features = legit_features + attack_features
df = pd.DataFrame(all_features)

# Amestecăm rândurile pentru un dataset mai realist
df = df.sample(frac=1, random_state=42).reset_index(drop=True)

df.to_csv('training/data/edos_features.csv', index=False)

print(f"\n=== Dataset salvat ===")
print(f"Total ferestre: {len(df)}")
print(f"Distribuție clase: legitim={sum(df['label']==0)}, atac={sum(df['label']==1)}")
print(f"Raport: {sum(df['label']==0)/len(df)*100:.1f}% legitim / {sum(df['label']==1)/len(df)*100:.1f}% atac")

print(f"\nStatistici per clasă:")
print(df.groupby('label').agg(['mean', 'std']).T)