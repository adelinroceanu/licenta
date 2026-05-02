"""
Generator de date sintetice care imită trafic 5G.
Rulează: python training/generate_synthetic_data.py
Ieșire: training/data/synthetic_traffic.csv
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Parametri
TOTAL_HOURS = 48              # 48 ore de date
SAMPLE_INTERVAL_SECONDS = 30  # un punct la fiecare 30 secunde
TOTAL_SAMPLES = TOTAL_HOURS * 3600 // SAMPLE_INTERVAL_SECONDS  # = 5760

# Generăm timpul
start_time = datetime(2026, 1, 1, 0, 0, 0)
timestamps = [start_time + timedelta(seconds=SAMPLE_INTERVAL_SECONDS * i)
              for i in range(TOTAL_SAMPLES)]

# Funcție utilitară: pattern diurn
def daily_pattern(t_seconds, baseline, peak, period_hours=24):
    """Pattern sinusoidal cu vârf la 14:00 și minim la 02:00"""
    period_seconds = period_hours * 3600
    phase = (t_seconds % period_seconds) / period_seconds
    # peak la phase=0.58 (~14:00), min la phase=0.08 (~02:00)
    sinusoid = np.sin(2 * np.pi * (phase - 0.33))
    return baseline + (peak - baseline) * (sinusoid + 1) / 2

# Generăm metricile
data = []
for i, ts in enumerate(timestamps):
    t_sec = (ts - start_time).total_seconds()

    # 1. Rata cererilor UE (UE/min): baseline 0.5, peak 2.0
    ue_rate = daily_pattern(t_sec, baseline=0.5, peak=2.0)
    ue_rate += np.random.normal(0, 0.15)  # zgomot
    ue_rate = max(0.1, ue_rate)

    # 2. Sesiuni PDU active: corelat cu UE rate, dar mai lent
    pdu_active = daily_pattern(t_sec, baseline=8, peak=18)
    pdu_active += np.random.normal(0, 1.0)
    pdu_active = max(2, pdu_active)

    # 3. Throughput user-plane (Mbps): proporțional cu sesiunile
    throughput = pdu_active * 8 + np.random.normal(0, 5)
    throughput = max(0, throughput)

    # 4. Utilizare CPU (procent): corelat cu UE rate + sesiuni
    cpu = 20 + ue_rate * 10 + pdu_active * 1.5 + np.random.normal(0, 3)
    cpu = np.clip(cpu, 5, 95)

    # 5. Utilizare memorie (procent): mai stabilă
    memory = 40 + pdu_active * 1.2 + np.random.normal(0, 1.5)
    memory = np.clip(memory, 30, 90)

    data.append({
        'timestamp': ts,
        'ue_rate': round(ue_rate, 3),
        'pdu_active': round(pdu_active, 1),
        'throughput_mbps': round(throughput, 2),
        'cpu_percent': round(cpu, 2),
        'memory_percent': round(memory, 2),
    })

# Salvăm în CSV
df = pd.DataFrame(data)
df.to_csv('training/data/synthetic_traffic.csv', index=False)

print(f"Generate {len(df)} puncte de date în training/data/synthetic_traffic.csv")
print(f"Perioada: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")
print(f"\nStatistici:")
print(df.describe())