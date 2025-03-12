import pandas as pd
import random
import os

# Global parameter for district name (can be set to None to process all districts)
DISTRICT_NAME = None  # Set to a specific district like 'KADIKÖY' or leave as None for all districts

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Paths relative to the script's directory
input_csv_path = os.path.join(script_dir, 'istanbul_buildings_with_unique_id.csv')
output_csv_path = os.path.join(script_dir, 'istanbul_all-selected-buildings.csv')

# Read the input CSV
df = pd.read_csv(input_csv_path, delimiter=';')

district_damage_cok_agir_h = {}
district_damage_agir_h = {}

# Filter for the specified district if DISTRICT_NAME is not None
if DISTRICT_NAME:
    df = df[df['ilce_adi'] == DISTRICT_NAME]

# Populate the dictionaries with the damage counts for each ilçe and mahalle
for district in df['ilce_adi'].unique():
    district_data = df[df['ilce_adi'] == district]
    # Aggregate building damage counts by 'mahalle_ad'
    mahalle_damage = district_data.groupby('mahalle_ad').agg({
        'cok_agir_h': 'max',  # Because buildings of the same mahalle have same damage count values for the mahalle
        'agir_hasar': 'max'
    }).reset_index()
    for _, row in mahalle_damage.iterrows():
        mahalle = row['mahalle_ad']
        cok_agir_h = row['cok_agir_h']
        agir_hasar = row['agir_hasar']
        if district not in district_damage_cok_agir_h:
            district_damage_cok_agir_h[district] = {}
            district_damage_agir_h[district] = {}
        district_damage_cok_agir_h[district][mahalle] = cok_agir_h
        district_damage_agir_h[district][mahalle] = agir_hasar

selected_building_ids = []

# Iterate through each ilçe and mahalle combination and randomly select buildings
for district, mahalle_damage in district_damage_cok_agir_h.items():
    # Filter buildings for the currently iterated ilçe
    district_buildings_df = df[df['ilce_adi'] == district]
    
    for mahalle, damage_count in mahalle_damage.items():
        # Select buildings randomly based on the number of completely damaged buildings in each mahalle
        mahalle_buildings = district_buildings_df[district_buildings_df['mahalle_ad'] == mahalle]['unique_id'].tolist()
        if len(mahalle_buildings) >= damage_count:
            selected_buildings = random.sample(mahalle_buildings, damage_count)
            selected_building_ids.extend(selected_buildings)

    for mahalle, damage_count in district_damage_agir_h[district].items():
        # Select buildings randomly based on the number of heavily damaged buildings in each mahalle
        mahalle_buildings = district_buildings_df[district_buildings_df['mahalle_ad'] == mahalle]['unique_id'].tolist()
        if len(mahalle_buildings) >= damage_count:
            selected_buildings = random.sample(mahalle_buildings, damage_count)
            selected_building_ids.extend(selected_buildings)

# Remove duplicates from the selected building IDs
selected_building_ids = list(set(selected_building_ids))

# Create a data frame for all selected buildings
selected_buildings_df = df[df['unique_id'].isin(selected_building_ids)]

# Save the randomly selected buildings to a single CSV file
selected_buildings_df.to_csv(output_csv_path, index=False, sep=';')

# Write the CSV to the specified output file
print(f"Selected buildings saved to: {output_csv_path}")
