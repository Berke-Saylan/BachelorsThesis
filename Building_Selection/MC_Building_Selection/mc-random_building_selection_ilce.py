"""
Monte Carlo-Based Earthquake Building Collapse Simulation
=========================================================

This script is part of a simulation estimating building collapses in a 7.5-magnitude earthquake scenario for Kadıköy, Istanbul. 
Since exact collapse predictions are impossible, the simulation relies on the IBB DEZİM Kadıköy (2020) dataset, which provides 
damage estimates per neighborhood. Buildings classified as very heavily or heavily damaged are assumed to be the most likely to collapse.

This version of the simulation employs Monte Carlo sampling, a stochastic method that randomly selects buildings based on the damage 
counts per neighborhood. By repeating this process multiple times, it generates varied yet statistically representative scenarios of 
potential collapses. 

Methodology:
------------
1. Read Dataset: Load building data including unique IDs, neighborhoods, and estimated damage levels.
2. Filter by District: Only buildings in Kadıköy are considered.
3. Compute Damage Levels: Aggregate buildings marked as very heavily and heavily damaged for each neighborhood.
4. Randomized Selection:
    - Buildings are randomly sampled based on damage counts using Monte Carlo simulation.
    - Selection is performed separately for "very heavy damage" and "heavy damage" categories.
    - Duplicate selections are removed to avoid over-counting.
5. Run Multiple Simulations: The process is repeated NUM_SIMULATIONS times with different random seeds.
6. Output GeoJSON Files: Each simulation result is stored as a GeoJSON file for further analysis.

"""
import pandas as pd
import random
import json
import os

# Global parameter for district name
DISTRICT_NAME = 'KADIKÖY'  # Change this if needed

NUM_SIMULATIONS = 10

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Input CSV path (go one level up)
input_csv_path = os.path.join(script_dir, '..', 'istanbul_buildings_with_unique_id.csv')

# Normalize the path to handle different OS directory structures
input_csv_path = os.path.abspath(input_csv_path)

# Output directory (to store the 100 GeoJSON files)
output_dir = os.path.join(script_dir, 'mc_selected_10_buildings')
os.makedirs(output_dir, exist_ok=True)

# Read input CSV
try:
    df = pd.read_csv(input_csv_path, delimiter=';')
except Exception as e:
    print(f"Error reading the input CSV file: {e}")
    raise

# Filter DataFrame to only include buildings in the specified district
df_district = df[df['ilce_adi'] == DISTRICT_NAME]

# Prepare dictionaries to store damage counts
district_damage_cok_agir_h = {}
district_damage_agir_h = {}

# Aggregate building damage counts by 'mahalle_ad' for the specified district
mahalle_damage = df_district.groupby('mahalle_ad').agg({
    'cok_agir_h': 'max',
    'agir_hasar': 'max'
}).reset_index()

for _, row in mahalle_damage.iterrows():
    mahalle = row['mahalle_ad']
    cok_agir_h = row['cok_agir_h']
    agir_hasar = row['agir_hasar']
    if DISTRICT_NAME not in district_damage_cok_agir_h:
        district_damage_cok_agir_h[DISTRICT_NAME] = {}
        district_damage_agir_h[DISTRICT_NAME] = {}
    district_damage_cok_agir_h[DISTRICT_NAME][mahalle] = cok_agir_h
    district_damage_agir_h[DISTRICT_NAME][mahalle] = agir_hasar

# --------------------------------------------------------------------------
# Main loop: run the random selection logic 100 times with different seeds
# --------------------------------------------------------------------------
for i in range(1, NUM_SIMULATIONS + 1):
    # Use a specific random seed for each iteration to vary the results
    random.seed(i)

    selected_building_ids = []

    # First pass: sample buildings according to 'cok_agir_h'
    for mahalle, damage_count in district_damage_cok_agir_h[DISTRICT_NAME].items():
        mahalle_buildings = df_district[df_district['mahalle_ad'] == mahalle]['unique_id'].tolist()
        if len(mahalle_buildings) >= damage_count:
            selected_buildings = random.sample(mahalle_buildings, damage_count)
            selected_building_ids.extend(selected_buildings)

    # Second pass: sample buildings according to 'agir_hasar'
    for mahalle, damage_count in district_damage_agir_h[DISTRICT_NAME].items():
        mahalle_buildings = df_district[df_district['mahalle_ad'] == mahalle]['unique_id'].tolist()
        if len(mahalle_buildings) >= damage_count:
            selected_buildings = random.sample(mahalle_buildings, damage_count)
            selected_building_ids.extend(selected_buildings)

    # Remove duplicates
    selected_building_ids = list(set(selected_building_ids))

    # ---------------------------------------------------------
    # Create a GeoJSON structure with a CRS block
    # ---------------------------------------------------------
    geojson_data = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {
                "name": "EPSG:4326"
            }
        },
        "features": []
    }

    # Filter the master DataFrame by these selected building IDs
    selected_rows = df[df['unique_id'].isin(selected_building_ids)]

    # Add the selected buildings to the GeoJSON
    for _, row in selected_rows.iterrows():
        # Ensure coordinates are [longitude, latitude], with correct decimal points
        # If row['Centroid_X'] ~ 29 and row['Centroid_Y'] ~ 40, it's probably [lon, lat].
        lon_val = float(str(row['Centroid_X']).replace(',', '.'))
        lat_val = float(str(row['Centroid_Y']).replace(',', '.'))

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon_val, lat_val]  # [longitude, latitude]
            },
            "properties": {
                "unique_id": row['unique_id'],
                "mahalle_ad": row['mahalle_ad'],
                "cok_agir_h": row['cok_agir_h'],
                "agir_hasar": row['agir_hasar']
            }
        }
        geojson_data["features"].append(feature)

    # Construct the full output path for this run
    output_geojson_path = os.path.join(
        output_dir,
        f'mc_selected_buildings_{DISTRICT_NAME.lower()}_{i}.geojson'
    )
    # Save the GeoJSON file
    try:
        with open(output_geojson_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=4)
        print(f"[Run {i}] Selected buildings saved to GeoJSON: {output_geojson_path}")
        print(f"[Run {i}] Total selected buildings: {len(selected_building_ids)}")
    except Exception as e:
        print(f"Error saving the GeoJSON file for run {i}: {e}")
        raise



