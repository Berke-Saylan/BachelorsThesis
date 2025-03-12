"""
GeoJSON to Shapefile Conversion with Buffering
=====================================================================

This script converts selected buildings from earthquake simulations (either Latin Hypercube Sampling (LHS) or Monte Carlo (MC)) 
from GeoJSON to Shapefiles (SHP), applying a 50-meter buffer to each dataset. The simulation method is determined by a boolean parameter.

- LHS outputs are processed from `LHS_Building_Selection/lhs_selected_10_building_buffers`.
- MC outputs are processed from `MC_Building_Selection/mc_selected_10_building_buffers`.

Methodology:
------------
1. Determine Selection Method: The script checks if LHS or MC is used based on the boolean parameter.
2. Set Up Paths**:
    - Uses **relative paths** based on the script's local environment to ensure machine independence.
3. Process GeoJSON Files:
    - Converts each GeoJSON file to a Shapefile (SHP).
    - Applies a 50-meter buffer with overlapping buffers dissolved.
4. Save Outputs:
    - Buffers are stored as shapefiles in `LHS_Building_Selection/lhs_selected_10_building_buffers` or `MC_Building_Selection/mc_selected_10_building_buffers`.
    - You can directly use these output shp files by establishing a folder connection with the current directory in your ArcGIS map workspace.
Important Note:
---------------
LOCAL SHAPEFILE USAGE
- This script assumes you have your own directory structure for storing SHP files instead of a Geodatabase.
- The author uses local paths for input/output.
- **You should create your own directory structure** and update the script accordingly.

"""

import arcpy
import os

# Boolean to choose selection method
USE_LHS = False  # Set to False for Monte Carlo method

# Global parameters
DISTRICT_NAME = 'KADIKÖY'  # Change this if needed
NUM_SIMULATIONS = 2  # Number of simulations

district_name_lower = DISTRICT_NAME.lower()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Set input and output folders based on method
if USE_LHS:
    geojson_folder = os.path.join(script_dir, "LHS_Building_Selection", "lhs_selected_10_buildings")
    shp_output_folder = os.path.join(script_dir, "LHS_Building_Selection", "lhs_selected_10_building_buffers")
    filename_template = f"lhs_selected_buildings_{district_name_lower}_{{}}.geojson"
else:
    geojson_folder = os.path.join(script_dir, "MC_Building_Selection", "mc_selected_10_buildings")
    shp_output_folder = os.path.join(script_dir, "MC_Building_Selection", "mc_selected_10_building_buffers")
    filename_template = f"mc_selected_buildings_{district_name_lower}_{{}}.geojson"

# Ensure the output folder exists
os.makedirs(shp_output_folder, exist_ok=True)

# Buffer distance (50 meters)
buffer_distance = "50 Meters"

# Loop through simulations (1 to NUM_SIMULATIONS)
for i in range(1, NUM_SIMULATIONS + 1):
    geojson_file = os.path.join(geojson_folder, filename_template.format(i))
    output_shp = os.path.join(shp_output_folder, filename_template.format(i).replace(".geojson", ".shp"))
    buffer_shp = os.path.join(shp_output_folder, filename_template.format(i).replace(".geojson", "_buffer.shp"))

    # Check if file exists
    if os.path.exists(geojson_file):
        print(f"Processing: {geojson_file}")

        try:
            # Step 1: Convert GeoJSON to Shapefile
            arcpy.conversion.JSONToFeatures(geojson_file, output_shp, "POINT")
            print(f"Converted: {geojson_file} → {output_shp}")

            # Step 2: Create 50m Buffer with Dissolve
            arcpy.analysis.Buffer(output_shp, buffer_shp, buffer_distance, 
                                  "FULL", "ROUND", "ALL")  # "ALL" dissolves overlapping buffers
            print(f"Buffer created: {buffer_shp}")

        except Exception as e:
            print(f"Error processing {geojson_file}: {e}")
    else:
        print(f"File not found: {geojson_file}")

print("Conversion and Buffering Completed.")








