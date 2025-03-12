"""
Latin Hypercube Sampling-Based Earthquake Building Collapse Simulation
======================================

This script is part of a simulation estimating building collapses in a 7.5-magnitude earthquake scenario for Kadıköy, Istanbul. 
Since exact collapse predictions are impossible, the simulation relies on the IBB DEZİM Kadıköy (2020) dataset, which provides 
damage estimates per neighborhood. Buildings classified as very heavily or heavily damaged are assumed to be the most likely to collapse.

To select buildings, the script applies K-means clustering to divide each neighborhood into segments and then employs 
Latin Hypercube Sampling (LHS) to ensure proportional and evenly distributed selection. This approach minimizes bias, ensuring 
a realistic and spatially distributed representation of potential collapses.

Methodology:
------------
1. Read Dataset: The script loads the dataset containing buildings and their estimated damage levels.
2. Filter by District: Only buildings in Kadıköy are considered.
3. Compute Damage Levels: The script aggregates buildings marked as very heavily and heavily damaged for each neighborhood.
4. Coordinate Conversion: Ensures centroid coordinates are properly formatted for spatial processing.
5. K-means Clustering & LHS:
    - K-means clustering groups buildings into spatially coherent clusters.
    - Latin Hypercube Sampling (LHS) selects a proportional number of buildings from each cluster to ensure diversity and spatial balance.
6. Run Multiple Simulations: The process is repeated NUM_SIMULATIONS times to generate different collapse scenarios.
7. Output GeoJSON Files: Each simulation result is stored as a GeoJSON file for further analysis.

"""
import pandas as pd
import os
import json
from pyDOE import lhs
import numpy as np
from sklearn.cluster import KMeans

# Global parameter for district name
DISTRICT_NAME = 'KADIKÖY'

NUM_SIMULATIONS = 10

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Input CSV path (go one level up)
input_csv_path = os.path.join(script_dir, '..', 'istanbul_buildings_with_unique_id.csv')

# Normalize the path to handle different OS directory structures
input_csv_path = os.path.abspath(input_csv_path)

# Output directory (will contain 1..100 runs)
output_dir = os.path.join(script_dir, 'lhs_selected_10_buildings')
os.makedirs(output_dir, exist_ok=True)

# Read input CSV once
df = pd.read_csv(input_csv_path, delimiter=';')
df_district = df[df['ilce_adi'] == DISTRICT_NAME]

# Dictionary to hold damage count per mahalle
district_damage = {}

# Gather damage counts for both types of damages
mahalle_damage = df_district.groupby('mahalle_ad').agg({
    'cok_agir_h': 'max',
    'agir_hasar': 'max'
}).reset_index()

for _, row in mahalle_damage.iterrows():
    mahalle = row['mahalle_ad']
    # Total damage count from both columns
    total_damage_count = row['cok_agir_h'] + row['agir_hasar']
    district_damage[mahalle] = total_damage_count

# Ensure coordinates are in float format by replacing commas and converting
df_district['Centroid_X'] = df_district['Centroid_X'].str.replace(',', '.').astype(float)
df_district['Centroid_Y'] = df_district['Centroid_Y'].str.replace(',', '.').astype(float)

# Function to apply stratified LHS
def lhs_stratified_selection(buildings, coords, damage_count, random_state=42):
    k = min(max(1, len(buildings) // 4), damage_count)
    # Apply k-means clustering
    kmeans = KMeans(n_clusters=k, random_state=random_state).fit(coords)
    buildings['cluster'] = kmeans.labels_

    selected = []
    # Sampling proportionally from each cluster
    sample_per_cluster = max(1, damage_count // k)

    for cluster_id in range(k):
        cluster_buildings = buildings[buildings['cluster'] == cluster_id]
        actual_sample_size = min(len(cluster_buildings), sample_per_cluster)
        if actual_sample_size > 0:
            lhs_sample = lhs_selection(cluster_buildings['unique_id'].tolist(),
                                       actual_sample_size)
            selected.extend(lhs_sample)
    return selected

# Helper function to apply LHS
def lhs_selection(building_ids, sample_size):
    n_buildings = len(building_ids)
    if sample_size >= n_buildings:
        return building_ids
    # Latin Hypercube Sampling in one dimension
    sample_points = lhs(1, samples=sample_size)
    selected_indices = np.floor(sample_points * n_buildings).astype(int).flatten()
    return [building_ids[i] for i in selected_indices]

# Main loop: generate 100 different selections with random states
for i in range(1, NUM_SIMULATIONS + 1):
    all_selected_building_ids = []

    # Select buildings in each mahalle
    for mahalle, damage_count in district_damage.items():
        mahalle_df = df_district[df_district['mahalle_ad'] == mahalle]
        coords = mahalle_df[['Centroid_X', 'Centroid_Y']].values

        # Run the LHS-based cluster sampling
        selected_buildings = lhs_stratified_selection(
            mahalle_df[['unique_id']].copy(),
            coords,
            damage_count,
            random_state=i  # Different random state each iteration
        )
        all_selected_building_ids.extend(selected_buildings)

    # Make unique
    all_selected_building_ids = list(set(all_selected_building_ids))

    # Build the GeoJSON
    geojson_data = {
        "type": "FeatureCollection",
        "features": []
    }
    # Filter main df by selected ids
    selected_rows = df[df['unique_id'].isin(all_selected_building_ids)]

    for _, row in selected_rows.iterrows():
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    float(str(row['Centroid_X']).replace(',', '.')),
                    float(str(row['Centroid_Y']).replace(',', '.'))
                ]
            },
            "properties": {
                "unique_id": row['unique_id'],
                "mahalle_ad": row['mahalle_ad'],
                "cok_agir_h": row['cok_agir_h'],
                "agir_hasar": row['agir_hasar']
            }
        }
        geojson_data["features"].append(feature)

    # Save each run's GeoJSON into lhs_selected_100_buildings, numbered 1..100
    output_geojson_path = os.path.join(
        output_dir,
        f'lhs_selected_buildings_{DISTRICT_NAME.lower()}_{i}.geojson'
    )
    with open(output_geojson_path, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=4)

    print(f"[Run {i}] GeoJSON file saved: {output_geojson_path}")
    print(f"[Run {i}] Total selected buildings: {len(all_selected_building_ids)}")





