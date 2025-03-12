"""
Output Data Processing for LHS (or MC) Solutions:
Collects and aggregates solution files (y, R, x), calculates means/standard deviations,
and merges coordinates from demand data. Exports CSVs and Shapefiles for mapping.

"""

import pandas as pd
import numpy as np
import glob
import os
import geopandas as gpd
from shapely.geometry import Point

# User / Path Parameters
method = "LHS"                 # or "MC"
district_name_lower = "kadiköy"
script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)

# Solution files directory, e.g.:
#   .../Gurobi_Optimization_SLMRND/Output_Data_Files/lhs_output_files_gurobi
solution_dir = os.path.join(
    base_dir,
    "Gurobi_Optimization_SLMRND",
    "Output_Data_Files",
    f"{method.lower()}_output_files_gurobi"
)

# Example glob patterns for solution CSVs:
y_solution_files = glob.glob(os.path.join(solution_dir, f"{method}_{district_name_lower}_y_solution_scenarios_*.csv"))
r_solution_files = glob.glob(os.path.join(solution_dir, f"{method}_{district_name_lower}_R_solution_scenarios_*.csv"))
x_solution_files = glob.glob(os.path.join(solution_dir, f"{method}_{district_name_lower}_x_solution_scenarios_*.csv"))

# Demand data file for coordinate lookup (choose any scenario to extract POD coords)
# Example:  .../Building_Selection/LHS_Building_Selection/lhs_LDC_POD_DemandPoint_csv/LHS_LDC_POD_DemandPoint_kadiköy_Scenario_1.csv
demand_data_file = os.path.join(
    base_dir,
    "Building_Selection",
    f"{method}_Building_Selection",
    f"{method.lower()}_LDC_POD_DemandPoint_csv",
    f"{method}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_1.csv"
)

# Load Demand Data (for coordinates)
demand_data = pd.read_csv(demand_data_file, delimiter=',')
# Ensure 'X','Y' are numeric
demand_data['X'] = pd.to_numeric(demand_data['X'], errors='coerce')
demand_data['Y'] = pd.to_numeric(demand_data['Y'], errors='coerce')
demand_data.set_index(demand_data.columns[0], inplace=True)  # assume first column is OID_ or similar

# Compute Mean of y_solution Across Files
pod_sum, pod_count = {}, {}
for file in y_solution_files:
    try:
        df = pd.read_csv(file)
        for _, row in df.iterrows():
            pod, y_val = row['POD'], row['y_value']
            pod_sum[pod] = pod_sum.get(pod, 0) + y_val
            pod_count[pod] = pod_count.get(pod, 0) + 1
    except Exception as e:
        print(f"Skipping file {file} due to: {e}")

pod_mean = {p: pod_sum[p]/pod_count[p] for p in pod_sum}
mean_df = pd.DataFrame(list(pod_mean.items()), columns=['POD', 'Mean_y_value'])
mean_df.to_csv(f"{method}_mean_y_values.csv", index=False)

# Pick top 100
top_pods = sorted(pod_mean.items(), key=lambda x: x[1], reverse=True)[:100]
top_pods_ids = {pod for pod, _ in top_pods}
aggregated_data = {p: 1 if p in top_pods_ids else 0 for p in pod_mean}
aggregated_df = pd.DataFrame(list(aggregated_data.items()), columns=['POD', 'Aggregated_y_value'])
aggregated_df.to_csv(f"{method}_aggregated_y_solution.csv", index=False)

# Compute Std Dev for R_solution
pod_r_values = {}
for file in r_solution_files:
    try:
        df = pd.read_csv(file)
        for _, row in df.iterrows():
            pod, r_val = row['POD'], row['R_value']
            pod_r_values.setdefault(pod, []).append(r_val)
    except Exception as e:
        print(f"Skipping file {file} due to: {e}")

pod_sd = {p: np.std(vals) for p, vals in pod_r_values.items()}
sd_df = pd.DataFrame(list(pod_sd.items()), columns=['POD', 'Standard_Deviation'])
sd_df.to_csv(f"{method}_POD_standard_deviations.csv", index=False)

# Mean R_value
pod_mean_r = {p: np.mean(vals) for p, vals in pod_r_values.items()}
mean_r_df = pd.DataFrame(list(pod_mean_r.items()), columns=['POD', 'Mean_R_value'])
combined_df = mean_r_df.merge(demand_data[['X','Y']], left_on='POD', right_index=True, how='left')
combined_df.to_csv(f"{method}_mean_R_values_with_coordinates.csv", index=False)

# Merge Coordinates for x_solution
def merge_coordinates_for_x(df, demand_data):
    df = df.merge(demand_data[['X','Y']], left_on='POD', right_index=True, how='left')
    df.rename(columns={'X': 'POD_X', 'Y': 'POD_Y'}, inplace=True)
    df = df.merge(demand_data[['X','Y']], left_on='Demand_Node', right_index=True, how='left')
    df.rename(columns={'X': 'Demand_X', 'Y': 'Demand_Y'}, inplace=True)
    return df

# Compute Mean x_value
x_value_sum, x_value_count = {}, {}
for file in x_solution_files:
    try:
        df = pd.read_csv(file)
        for _, row in df.iterrows():
            key = (row['Demand_Node'], row['POD'])
            x_value_sum[key] = x_value_sum.get(key, 0) + row['x_value']
            x_value_count[key] = x_value_count.get(key, 0) + 1
    except Exception as e:
        print(f"Skipping file {file} due to: {e}")

mean_x_values = {k: x_value_sum[k]/x_value_count[k] for k in x_value_sum}
mean_x_df = pd.DataFrame([(dn, p, val) for (dn, p), val in mean_x_values.items()],
                         columns=['Demand_Node','POD','Mean_x_value'])
mean_x_df = merge_coordinates_for_x(mean_x_df, demand_data)

# Save as shapefile
mean_x_df['geometry'] = mean_x_df.apply(lambda r: Point(r['POD_X'], r['POD_Y']), axis=1)
mean_x_gdf = gpd.GeoDataFrame(mean_x_df, geometry='geometry', crs="EPSG:4326")
mean_x_gdf.to_file(f"{method}_mean_x_values_with_coordinates.shp", driver='ESRI Shapefile')

# Aggregate x_value = 1
aggregated_data_x = set()
for file in x_solution_files:
    try:
        df = pd.read_csv(file)
        sel = df[df['x_value'] == 1][['Demand_Node', 'POD']]
        aggregated_data_x.update(map(tuple, sel.values))
    except Exception as e:
        print(f"Skipping file {file} due to: {e}")

aggregated_x_df = pd.DataFrame(list(aggregated_data_x), columns=['Demand_Node','POD'])
aggregated_x_df['Aggregated_x_value'] = 1
aggregated_x_df = merge_coordinates_for_x(aggregated_x_df, demand_data)
aggregated_x_df['geometry'] = aggregated_x_df.apply(lambda r: Point(r['POD_X'], r['POD_Y']), axis=1)
aggregated_gdf = gpd.GeoDataFrame(aggregated_x_df, geometry='geometry', crs="EPSG:4326")
aggregated_gdf.to_file(f"{method}_aggregated_x_solution_with_coordinates.shp", driver='ESRI Shapefile')

# Save y=1 PODs to Shapefile
def save_to_shapefile(pods, output_filename):
    selected = demand_data.loc[pods].reset_index()
    selected['geometry'] = selected.apply(lambda r: Point(r['X'], r['Y']), axis=1)
    gdf = gpd.GeoDataFrame(selected, geometry='geometry', crs="EPSG:4326")
    gdf.to_file(output_filename, driver='ESRI Shapefile')
    print(f"Saved: {output_filename}")

for y_file in y_solution_files:
    df = pd.read_csv(y_file)
    selected_pods = df[df['y_value'] == 1]['POD'].tolist()
    scenario_name = os.path.splitext(os.path.basename(y_file))[0]
    shp_name = f"{scenario_name}_selected_pods.shp"
    save_to_shapefile(selected_pods, shp_name)

# Save aggregated y=1
aggregated_y_df = pd.read_csv(f"{method}_aggregated_y_solution.csv")
selected_agg_pods = aggregated_y_df[aggregated_y_df['Aggregated_y_value'] == 1]['POD'].tolist()
save_to_shapefile(selected_agg_pods, f"{method}_aggregated_y_solution_selected_pods.shp")

print("Processing complete.")
