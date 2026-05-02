"""
Antrenare model GRU pentru predicția traficului 5G.
Rulează: python training/train_gru.py
Ieșiri:
  - training/models/gru_forecaster.h5  (modelul antrenat)
  - training/models/scaler_params.npz  (parametri standardizare)
  - training/models/training_history.png (grafic loss)
"""
import numpy as np
import pandas as pd
import tensorflow as tf
import matplotlib.pyplot as plt

# ---------- Parametri ----------
INPUT_WINDOW = 30   # 30 pași = 15 minute istoric
OUTPUT_HORIZON = 10 # 10 pași = 5 minute predicție
FEATURES = ['ue_rate', 'pdu_active', 'throughput_mbps', 'cpu_percent', 'memory_percent']
N_FEATURES = len(FEATURES)

EPOCHS = 100
BATCH_SIZE = 64
LEARNING_RATE = 1e-3

# ---------- Citire date ----------
print("=== Citire date ===")
df = pd.read_csv('training/data/synthetic_traffic.csv')
print(f"Total puncte: {len(df)}")

# Extragere features
data = df[FEATURES].values.astype(np.float32)
print(f"Shape date: {data.shape}")  # (5760, 5)

# ---------- Împărțire train/val/test ----------
print("\n=== Împărțire train/val/test ===")
n = len(data)
train_end = int(n * 0.70)
val_end = int(n * 0.85)

train_data = data[:train_end]
val_data = data[train_end:val_end]
test_data = data[val_end:]

print(f"Train: {len(train_data)}")
print(f"Val:   {len(val_data)}")
print(f"Test:  {len(test_data)}")

# ---------- Standardizare ----------
print("\n=== Standardizare ===")
mean = train_data.mean(axis=0)
std = train_data.std(axis=0)
print(f"Mean: {mean}")
print(f"Std:  {std}")

# Salvăm parametrii (vor fi folosiți la inferență)
np.savez('training/models/scaler_params.npz', mean=mean, std=std)

# Aplicăm standardizarea
train_scaled = (train_data - mean) / std
val_scaled = (val_data - mean) / std
test_scaled = (test_data - mean) / std

# ---------- Construire ferestre ----------
def make_windows(data, input_window, output_horizon):
    """Sliding window: input = INPUT_WINDOW pași, output = OUTPUT_HORIZON pași"""
    X, y = [], []
    for i in range(len(data) - input_window - output_horizon + 1):
        X.append(data[i:i+input_window])
        y.append(data[i+input_window:i+input_window+output_horizon])
    return np.array(X), np.array(y)

print("\n=== Construire ferestre ===")
X_train, y_train = make_windows(train_scaled, INPUT_WINDOW, OUTPUT_HORIZON)
X_val, y_val = make_windows(val_scaled, INPUT_WINDOW, OUTPUT_HORIZON)
X_test, y_test = make_windows(test_scaled, INPUT_WINDOW, OUTPUT_HORIZON)

print(f"X_train shape: {X_train.shape}")  # (~4000, 30, 5)
print(f"y_train shape: {y_train.shape}")  # (~4000, 10, 5)

# Reshape y la format flatten pentru output dens (10 pași × 5 features = 50)
y_train_flat = y_train.reshape(y_train.shape[0], -1)
y_val_flat = y_val.reshape(y_val.shape[0], -1)
y_test_flat = y_test.reshape(y_test.shape[0], -1)

# ---------- Construire model ----------
print("\n=== Construire model GRU ===")
model = tf.keras.Sequential([
    tf.keras.layers.GRU(64, return_sequences=True,
                        input_shape=(INPUT_WINDOW, N_FEATURES)),
    tf.keras.layers.GRU(64),
    tf.keras.layers.Dense(OUTPUT_HORIZON * N_FEATURES, activation='linear')
])

model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
    loss='mse',
    metrics=['mae']
)

model.summary()

# ---------- Antrenare ----------
print("\n=== Antrenare ===")
early_stop = tf.keras.callbacks.EarlyStopping(
    monitor='val_loss', patience=10, restore_best_weights=True, verbose=1
)

history = model.fit(
    X_train, y_train_flat,
    validation_data=(X_val, y_val_flat),
    epochs=EPOCHS,
    batch_size=BATCH_SIZE,
    callbacks=[early_stop],
    verbose=1
)

# ---------- Salvare model ----------
print("\n=== Salvare model ===")
model.save('training/models/gru_forecaster.h5')
print("Model salvat: training/models/gru_forecaster.h5")

# ---------- Evaluare pe test ----------
print("\n=== Evaluare pe set de test ===")
test_loss, test_mae = model.evaluate(X_test, y_test_flat, verbose=0)
print(f"Test MSE: {test_loss:.4f}")
print(f"Test MAE: {test_mae:.4f}")

# Calculăm și MAPE manual
y_pred_flat = model.predict(X_test, verbose=0)
y_pred = y_pred_flat.reshape(-1, OUTPUT_HORIZON, N_FEATURES)

# Denormalizare pentru MAPE
y_test_real = y_test * std + mean
y_pred_real = y_pred * std + mean

# MAPE per feature
print("\nMAPE per feature:")
for i, feat in enumerate(FEATURES):
    real = y_test_real[:, :, i]
    pred = y_pred_real[:, :, i]
    mape = np.mean(np.abs((real - pred) / (real + 1e-6))) * 100
    print(f"  {feat:20s}: {mape:.2f}%")

# MAPE global
mape_global = np.mean(np.abs((y_test_real - y_pred_real) / (y_test_real + 1e-6))) * 100
print(f"  {'AGGREGATE':20s}: {mape_global:.2f}%")

# ---------- Plot training history ----------
print("\n=== Generare grafic ===")
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
plt.plot(history.history['loss'], label='Train Loss')
plt.plot(history.history['val_loss'], label='Val Loss')
plt.xlabel('Epoch')
plt.ylabel('MSE Loss')
plt.title('Training Loss')
plt.legend()
plt.grid(True, alpha=0.3)

plt.subplot(1, 2, 2)
plt.plot(history.history['mae'], label='Train MAE')
plt.plot(history.history['val_mae'], label='Val MAE')
plt.xlabel('Epoch')
plt.ylabel('MAE')
plt.title('Training MAE')
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('training/models/training_history.png', dpi=100)
print("Grafic salvat: training/models/training_history.png")

print("\n=== TERMINAT ===")
print("Pentru a testa modelul vizual, rulează: python training/visualize_predictions.py")