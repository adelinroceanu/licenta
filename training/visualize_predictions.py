"""
Vizualizare predicții GRU vs realitate.
Rulează: python training/visualize_predictions.py
Ieșire: training/models/predictions_plot.png
"""
import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt

# Parametri (trebuie să corespundă cu cei din train_gru.py)
INPUT_WINDOW = 30
OUTPUT_HORIZON = 10
FEATURES = ['ue_rate', 'pdu_active', 'throughput_mbps', 'cpu_percent', 'memory_percent']
N_FEATURES = len(FEATURES)

# Încarcă model + scaler
print("=== Încărcare model ===")
model = tf.keras.models.load_model('training/models/gru_forecaster.h5')
scaler = np.load('training/models/scaler_params.npz')
mean, std = scaler['mean'], scaler['std']

# Încarcă date test
print("=== Încărcare date ===")
df = pd.read_csv('training/data/synthetic_traffic.csv')
data = df[FEATURES].values.astype(np.float32)
n = len(data)
test_data = data[int(n * 0.85):]
test_scaled = (test_data - mean) / std

# Predicție pas cu pas
print("=== Generare predicții ===")
predictions = []
realities = []
timestamps = []

for i in range(0, len(test_scaled) - INPUT_WINDOW - OUTPUT_HORIZON, OUTPUT_HORIZON):
    # Input: 30 pași istoric
    X = test_scaled[i:i+INPUT_WINDOW].reshape(1, INPUT_WINDOW, N_FEATURES)
    # Predicție
    y_pred_scaled = model.predict(X, verbose=0).reshape(OUTPUT_HORIZON, N_FEATURES)
    y_pred = y_pred_scaled * std + mean
    # Realitate
    y_real = test_data[i+INPUT_WINDOW:i+INPUT_WINDOW+OUTPUT_HORIZON]

    predictions.append(y_pred)
    realities.append(y_real)

predictions = np.concatenate(predictions, axis=0)
realities = np.concatenate(realities, axis=0)

# Plot pentru fiecare feature
print("=== Generare grafice ===")
fig, axes = plt.subplots(N_FEATURES, 1, figsize=(12, 2.5 * N_FEATURES))

for i, feat in enumerate(FEATURES):
    ax = axes[i]
    ax.plot(realities[:200, i], label='Real', color='#185FA5', linewidth=1.5)
    ax.plot(predictions[:200, i], label='Predicție GRU', color='#BA7517',
            linewidth=1.5, linestyle='--')
    ax.set_title(f'{feat}')
    ax.set_xlabel('Pas timp (30 secunde fiecare)')
    ax.set_ylabel(feat)
    ax.legend()
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('training/models/predictions_plot.png', dpi=100, bbox_inches='tight')
print("Grafic salvat: training/models/predictions_plot.png")

# Statistici
print("\n=== Statistici finale ===")
for i, feat in enumerate(FEATURES):
    real = realities[:, i]
    pred = predictions[:, i]
    mape = np.mean(np.abs((real - pred) / (real + 1e-6))) * 100
    rmse = np.sqrt(np.mean((real - pred) ** 2))
    print(f"  {feat:20s}: MAPE={mape:5.2f}%  RMSE={rmse:.3f}")