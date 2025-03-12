"""
Spatial Join and Point Conversion for Demand Calculation Based on Population/4 + [Number of Collapsed BUildings in 150m Radius] * 50
=====================================================

This script processes buffered buildings selected from earthquake simulations (LHS or Monte Carlo) and performs a spatial join 
with demand points. The workflow includes:

- Reading input SHP files from `LHS_Building_Selection/lhs_selected_10_building_buffers` or `MC_Building_Selection/mc_selected_10_building_buffers`.
- Performing a spatial join** between selected buildings and buffer layers.
- Converting the result into a point feature class with demand calculations.
- Cleaning up unnecessary fields and removing intermediate files.

Methodology:
------------
1. Load Input Data: 
    - Reads selected buildings (LHS/MC) and buffered demand points.
2. Perform Spatial Join**:
    - Joins selected buildings to the buffer layer.
    - Keeps relevant fields such as X, Y, Population, Area, and Join_Count.
3. Convert Joined Features to Points:
    - Extracts coordinates to create a point feature class.
4. Compute Demand Field:
    - Adds a `Demand` field and calculates values based on `Population` and `Join_Count`.
5. Cleanup:
    - Removes intermediate fields and deletes unnecessary polygon layers.

Important Note:
---------------
 LOCAL GEOJSON USAGE
- This script assumes the spatial join is applied to a GeoJSON buffer file instead of a Geodatabase.
- Modify the `buffer_geojson` and `shp_output_folder` paths accordingly.

"""
import arcpy
import os
import csv

arcpy.env.overwriteOutput = True

# Boolean to choose selection method
USE_LHS = False  # Set to False for Monte Carlo method

# Global parameters
DISTRICT_NAME = 'KADIKÖY'  # Change this if needed
NUM_SIMULATIONS = 2  # Number of simulations

district_name_lower = DISTRICT_NAME.lower()
method_prefix = "LHS" if USE_LHS else "MC"

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Set input and output folders based on method
if USE_LHS:
    buildings_folder = os.path.join(script_dir, "LHS_Building_Selection", "lhs_selected_10_buildings")  # <- Corrected
    shp_output_folder = os.path.join(script_dir, "LHS_Building_Selection", "lhs_LDC_POD_DemandPoint_data")
    csv_output_folder = os.path.join(script_dir, "LHS_Building_Selection", "lhs_LDC_POD_DemandPoint_csv")
else:
    buildings_folder = os.path.join(script_dir, "MC_Building_Selection", "mc_selected_10_buildings")  # <- Corrected
    shp_output_folder = os.path.join(script_dir, "MC_Building_Selection", "mc_LDC_POD_DemandPoint_data")
    csv_output_folder = os.path.join(script_dir, "MC_Building_Selection", "mc_LDC_POD_DemandPoint_csv")

# Path to the buffer GeoJSON file
buffer_geojson = os.path.join(script_dir, "LDC_POD_DemandPoint_kadiköy_buffer.json")

# Ensure output folders exist
os.makedirs(shp_output_folder, exist_ok=True)
os.makedirs(csv_output_folder, exist_ok=True)

# Convert GeoJSON buffer to a shapefile (if not already converted)
buffer_shp = os.path.join(shp_output_folder, "LDC_POD_DemandPoint_kadiköy_buffer.shp")
if not arcpy.Exists(buffer_shp):
    print("Converting buffer GeoJSON to Shapefile...")
    arcpy.conversion.JSONToFeatures(buffer_geojson, buffer_shp)
    print(f"Converted: {buffer_geojson} → {buffer_shp}")

# Loop through each selected buildings file (1 to NUM_SIMULATIONS)
for i in range(1, NUM_SIMULATIONS + 1):
    buildings_geojson = os.path.join(buildings_folder, f"{method_prefix.lower()}_selected_buildings_{district_name_lower}_{i}.geojson")
    buildings_shp = os.path.join(shp_output_folder, f"{method_prefix}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_{i}.shp")
    output_fc_polygons = os.path.join(shp_output_folder, f"{method_prefix}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_{i}_joined.shp")
    output_fc_points = os.path.join(shp_output_folder, f"{method_prefix}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_{i}_points.shp")
    csv_output_path = os.path.join(csv_output_folder, f"{method_prefix}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_{i}.csv")

    # Convert GeoJSON buildings file to Shapefile (if not already converted)
    if not arcpy.Exists(buildings_shp):
        print(f"Converting {buildings_geojson} to Shapefile...")
        arcpy.conversion.JSONToFeatures(buildings_geojson, buildings_shp, "POINT")
        print(f"Converted: {buildings_geojson} → {buildings_shp}")
        
    # Assign correct CRS if it's missing
    if arcpy.Describe(buildings_shp).spatialReference.name == "Unknown":
        print("Assigning GCS_WGS_1984 (EPSG:4326) to buildings shapefile...")
        arcpy.management.DefineProjection(buildings_shp, arcpy.SpatialReference(4326))


    if arcpy.Exists(buildings_shp):
        print(f"Processing Spatial Join for: {buildings_shp} with {buffer_shp}")

        try:
            # Create a FieldMappings object
            field_mappings = arcpy.FieldMappings()
            field_mappings.addTable(buffer_shp)
            field_mappings.addTable(buildings_shp)

            # Keep only required fields: X, Y, Population, Area, and Join Count
            fields_to_keep = ["X", "Y", "Population", "Area", "Join_Count"]
            for field_map_index in reversed(range(field_mappings.fieldCount)):
                field_name = field_mappings.getFieldMap(field_map_index).outputField.name
                if field_name not in fields_to_keep:
                    field_mappings.removeFieldMap(field_map_index)
            
            # Print coordinate systems of both datasets to debug and ensure that both data files have same coordinate systems
            print(f"Buildings CRS: {arcpy.Describe(buildings_shp).spatialReference.name}")
            print(f"Buffer CRS: {arcpy.Describe(buffer_shp).spatialReference.name}")

            # Step 1: Perform Spatial Join (Creates Polygons)
            arcpy.analysis.SpatialJoin(
                target_features=buffer_shp,
                join_features=buildings_shp,
                out_feature_class=output_fc_polygons,
                join_operation="JOIN_ONE_TO_ONE",
                join_type="KEEP_ALL",
                match_option="CONTAINS",
                field_mapping=field_mappings
            )
            print(f"Spatial Join completed → {output_fc_polygons}")

            # Step 2: Convert Polygons to Points Using X, Y Fields
            if arcpy.Exists(output_fc_points):
                arcpy.management.Delete(output_fc_points)  # Delete existing file before writing a new one

            arcpy.management.XYTableToPoint(
                in_table=output_fc_polygons,
                out_feature_class=output_fc_points,
                x_field="X",
                y_field="Y",
                coordinate_system=arcpy.SpatialReference(4326)
            )
            print(f"Converted to Points → {output_fc_points}")

            # Step 3: Add Demand Field and Calculate Values
            arcpy.management.AddField(output_fc_points, "Demand", "DOUBLE")
            with arcpy.da.UpdateCursor(output_fc_points, ["Population", "Join_Count", "Demand"]) as cursor:
                for row in cursor:
                    population = row[0]
                    join_count = row[1]
                    row[2] = 0 if population == 0 else (population / 4 + join_count * 50)
                    cursor.updateRow(row)
            print("Demand field calculated and updated.")

            # Step 4: Delete Unnecessary Fields
            arcpy.management.DeleteField(output_fc_points, ["Population", "Join_Count", "TARGET_FID"])
            print("Deleted Population, Join_Count, and TARGET_FID fields.")

            # Step 5: Delete Intermediate Polygon Feature Class
            arcpy.management.Delete(output_fc_polygons)
            print(f"Deleted intermediate polygon feature class: {output_fc_polygons}")

            # Step 6: Export to CSV with required fields
            required_fields = ["FID", "X", "Y", "Area", "Demand"]
            csv_headers = ["OBJECTID", "X", "Y", "Area", "Demand"]  # Renaming OBJECTID_1 to OBJECTID

            with open(csv_output_path, mode="w", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(csv_headers)  # Write header row

                with arcpy.da.SearchCursor(output_fc_points, required_fields) as cursor:
                    for row in cursor:
                        writer.writerow(row)
            
            print(f"CSV file saved → {csv_output_path}")

        except Exception as e:
            print(f"Error with {buildings_shp}: {e}")

    else:
        print(f"Feature class not found: {buildings_shp}")

print("Spatial Join & Point Conversion Completed for all scenarios.")



