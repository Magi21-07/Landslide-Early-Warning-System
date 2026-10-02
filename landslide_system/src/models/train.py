import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pickle
import os

def main():
    print("Generating training dataset...")
    np.random.seed(42)
    n_samples = 10000

    # Feature ranges
    slope_degrees = np.random.uniform(0, 60, n_samples)
    elevation_m = np.random.uniform(0, 4000, n_samples)
    rainfall_3day_mm = np.random.uniform(0, 300, n_samples)
    rainfall_15day_mm = np.random.uniform(0, 600, n_samples)
    
    # Ensure monotonic constraint
    rainfall_15day_mm = np.maximum(rainfall_15day_mm, rainfall_3day_mm)

    # Derived physical threshold equation
    risk_score = (slope_degrees / 30)**1.8 + (rainfall_15day_mm / 200)
    y = (risk_score > 1.2).astype(int)

    X = np.column_stack((slope_degrees, elevation_m, rainfall_3day_mm, rainfall_15day_mm))

    print("Fitting Scaler...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print("Training RandomForestClassifier...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
    # RF does not strictly require scaling, but applying it to satisfy requirements
    clf.fit(X_scaled, y)

    # Save artifacts
    model_dir = os.path.dirname(__file__)
    model_path = os.path.join(model_dir, 'landslide_model.pkl')
    scaler_path = os.path.join(model_dir, 'scaler.pkl')
    
    with open(model_path, 'wb') as f:
        pickle.dump(clf, f)
        
    with open(scaler_path, 'wb') as f:
        pickle.dump(scaler, f)

    print(f"Model and scaler trained and saved to {model_dir}!")

if __name__ == '__main__':
    main()
