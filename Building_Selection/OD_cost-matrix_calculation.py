"""
OD Cost Matrix Calculation with Dynamic Barrier Buffers
=====================================================================

This script runs an Origin–Destination (OD) Cost Matrix analysis on a specified
network dataset, incorporating dynamic buffering for different building-collapse
(or disruption) scenarios. Depending on which buildings are collapsed or disrupted,
unique polygon barriers are applied to the network, scaling travel costs within
those areas (e.g., simulating road closures or congestion).

- LHS (Latin Hypercube Sampling) scenarios are handled under the 
  `LHS_Building_Selection` folder.
- MC (Monte Carlo) scenarios are handled under the 
  `MC_Building_Selection` folder.

Methodology
-----------
1. Determine Scenario Type
   A boolean parameter determines whether LHS or MC is used. This affects both the
   input folder for building data and the type of polygon barrier shapefiles that
   get loaded.

2. Set Up Paths
   - Relative paths are used for machine independence.
   - The script identifies where to find (a) the scenario points shapefile
     (origins/destinations) and (b) the corresponding buffer polygons that serve
     as network barriers (e.g., collapsed roads, slowed traffic).
   - A valid ArcGIS Network Dataset (a .gdb containing roads and travel attributes)
     is set as the primary workspace.

3. Select Origins and Destinations
   - Depending on the scenario (LDC to POD or POD to DemandPoints), features in the
     shapefile are filtered with SQL queries like `"FID" = 1` (for a single origin)
     or `"FID" >= 1 AND \"FID\" <= 173"` (for multiple destinations).

4. Create OD Cost Matrix
   - The script uses `arcpy.na.MakeODCostMatrixLayer()` with a chosen cost attribute,
     such as TruckingDuration.
   - U-turn policies and cutoffs can be configured depending on the analysis needs.

5. Load Barriers
   - Each polygon barrier shapefile represents an area with a scaled cost multiplier
     (for instance, `BarrierType = 1` and `Attr_TruckingDuration = 10`).
   - This simulates localized disruptions or congestion within the affected polygons.

6. Solve the OD Matrix
   - The solver computes travel costs from each origin to each destination,
     respecting any barrier-induced cost increases.

7. Export Results
   - The OD Lines sublayer is queried with a SearchCursor to retrieve each
     (OriginID, DestinationID, Total_TruckingDuration) tuple.
   - These are written to a CSV file for each scenario, enabling further analysis
     or data visualization.

How This Helps
--------------
By applying different buffer polygons (one per scenario), you can simulate
transportation disruptions in a local distribution network. The resulting
travel times or costs allow planners to assess how building collapses
or blockages impact accessibility between critical points like LDCs, PODs,
or demand centers.

Important Note
--------------
- Machine Independence: Paths rely on directories inferred from the
  current script location rather than absolute file paths.

- Geodatabase Dependency: A valid ArcGIS-compatible `.gdb` workspace is
  needed to store the OD Cost Matrix and sublayers.

- Field Ranges: SQL expressions for feature selection (e.g., `"FID" = 1"`,
  `"FID" <= 173"`, etc.) must match the IDs in your data.
"""

import arcpy
from arcpy import env
import os
import csv
import traceback

try:
    # User Parameters
    DISTRICT_NAME = "KADIKÖY"   # District name
    NUM_SIMULATIONS = 2         # How many scenario shapefiles you have
    USE_LHS = False              # Set False for MC approach
    is_LDC_to_POD = False        # True = LDC to POD, False = POD to DemandPoints
    impedance_attribute = "TruckingDuration"  # Adjust if needed

    # Path Setups
    # Script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Base directory (parent of script_dir)
    base_dir = os.path.dirname(script_dir)

    # Convert district name to lowercase
    district_name_lower = DISTRICT_NAME.lower()

    # Define method prefix
    method_prefix = "LHS" if USE_LHS else "MC"

    # Input folder
    # Example: ...\Building_Selection\LHS_Building_Selection\lhs_LDC_POD_DemandPoint_data
    input_folder = os.path.join(
        base_dir,
        "Building_Selection",
        f"{method_prefix}_Building_Selection",
        f"{method_prefix.lower()}_LDC_POD_DemandPoint_data"
    )

    # Output folder
    # Example: ...\Gurobi_Optimization_SLMRND\Input_Data_Files\lhs_input_files_gurobi\lhs_LDC-POD_Matrices
    output_subfolder = (
        f"{method_prefix.lower()}_LDC-POD_Matrices"
        if is_LDC_to_POD
        else f"{method_prefix.lower()}_POD-DemandPoint_Matrices"
    )
    output_folder = os.path.join(
        base_dir,
        "Gurobi_Optimization_SLMRND",
        "Input_Data_Files",
        f"{method_prefix.lower()}_input_files_gurobi",
        output_subfolder
    )
    os.makedirs(output_folder, exist_ok=True)

    # Network and Workspace Setup
    # Path to your network dataset .gdb
    # Example: ...\Network_Data\turkiye_network.gdb\Turkiye_Network\TNDS
    network_gdb = #ENTER YOUR OWN ARCGIS NETWORK DATASET
    network_dataset = os.path.join(network_gdb, "Turkiye_Network", "TNDS")

    # Use that .gdb as the workspace
    env.workspace = network_gdb
    env.overwriteOutput = True

    # If needed, ensure the .gdb exists
    if not arcpy.Exists(network_gdb):
        folder_for_gdb = os.path.dirname(network_gdb)
        gdb_name = os.path.basename(network_gdb)
        arcpy.management.CreateFileGDB(folder_for_gdb, gdb_name)

    # Search tolerance
    search_tolerance = "100 Meters"

    # MAIN PROCESS
    for i in range(1, NUM_SIMULATIONS + 1):

        # Input SHP Filepath Arrangement
        # Example: lhs_LDC_POD_DemandPoint_kadiköy_Scenario_1_points.shp
        input_shp = os.path.join(
            input_folder,
            f"{method_prefix}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_{i}_points.shp"
        )

        if not arcpy.Exists(input_shp):
            print(f"Warning: Input SHP not found for Scenario {i} → {input_shp}")
            continue

        # Output Filepath Arrangement
        if is_LDC_to_POD:
            output_csv = os.path.join(
                output_folder,
                f"{method_prefix}_LDC-POD_Matrix_{district_name_lower}_Scenario_{i}.csv"
            )
        else:
            output_csv = os.path.join(
                output_folder,
                f"{method_prefix}_POD-DemandPoint_Matrix_{district_name_lower}_Scenario_{i}.csv"
            )

        # Layer Names
        layer_name = f"OD_Matrix_{district_name_lower}_Scenario_{i}"
        origins_layer = f"origins_layer_{i}"
        destinations_layer = f"destinations_layer_{i}"

        # Make feature layers
        arcpy.management.MakeFeatureLayer(input_shp, origins_layer)
        arcpy.management.MakeFeatureLayer(input_shp, destinations_layer)

        # SELECTION LOGIC
        # For LDC to POD: origins = FID=1, destinations = FID in [1..173]
        # For POD to Demand: origins = FID in [1..173], destinations = FID in [1..950]
        if is_LDC_to_POD:
            sql_origins = '"FID" = 1'
            sql_destinations = '"FID" >= 1 AND "FID" <= 173'
        else:
            sql_origins = '"FID" >= 1 AND "FID" <= 173'
            sql_destinations = '"FID" >= 1 AND "FID" <= 950'

        arcpy.management.SelectLayerByAttribute(origins_layer, "NEW_SELECTION", sql_origins)
        arcpy.management.SelectLayerByAttribute(destinations_layer, "NEW_SELECTION", sql_destinations)

        # Create & Configure OD-Cost Matrix
        result_object = arcpy.na.MakeODCostMatrixLayer(
            in_network_dataset=network_dataset,
            out_network_analysis_layer=layer_name,
            impedance_attribute=impedance_attribute,
            default_cutoff=None,
            UTurn_policy="ALLOW_UTURNS"
        )

        layer_object = result_object.getOutput(0)
        sublayer_names = arcpy.na.GetNAClassNames(layer_object)
        origins_layer_name = sublayer_names["Origins"]
        destinations_layer_name = sublayer_names["Destinations"]
        lines_layer_name = sublayer_names["ODLines"]

        # Load origins & destinations
        arcpy.na.AddLocations(
            in_network_analysis_layer=layer_object,
            sub_layer=origins_layer_name,
            in_table=origins_layer,
            search_tolerance=search_tolerance
        )
        arcpy.na.AddLocations(
            in_network_analysis_layer=layer_object,
            sub_layer=destinations_layer_name,
            in_table=destinations_layer,
            search_tolerance=search_tolerance
        )

        # Sublayer for polygon barriers
        barriers_layer_name = sublayer_names["PolygonBarriers"]

        # Build the barriers folder path
        barriers_folder = os.path.join(
            base_dir,
            "Building_Selection",
            "LHS_Building_Selection" if USE_LHS else "MC_Building_Selection",
            "lhs_selected_10_building_buffers" if USE_LHS else "mc_selected_10_building_buffers"
        )

        # Construct the barrier shapefile path for this scenario
        # e.g. "lhs_selected_buildings_kadiköy_1_buffer.shp" (or "mc_selected_buildings_kadiköy_1_buffer.shp")
        polygon_barriers = os.path.join(
            barriers_folder,
            f'{"lhs" if USE_LHS else "mc"}_selected_buildings_{district_name_lower}_{i}_buffer.shp'
        )

        if arcpy.Exists(polygon_barriers):
            # Create field mappings for polygon barriers, set BarrierType=1 (scaled cost) and scale by 10
            field_mappings_barriers = arcpy.na.NAClassFieldMappings(layer_object, barriers_layer_name)
            field_mappings_barriers["BarrierType"].defaultValue = 1
            field_mappings_barriers["Attr_TruckingDuration"].defaultValue = 10

            arcpy.na.AddLocations(
                in_network_analysis_layer=layer_object,
                sub_layer=barriers_layer_name,
                in_table=polygon_barriers,
                field_mappings=field_mappings_barriers,
                search_tolerance=search_tolerance
            )
        else:
            print(f"Polygon barrier does not exist for Scenario {i}: {polygon_barriers}")

        # Solve OD-Cost Matrix
        arcpy.na.Solve(layer_object)

        # Extract lines of OD-Cost Matrix to CSV
        # "TruckingDuration" output field typically "Total_TruckingDuration"
        cost_field_name = "Total_TruckingDuration"
        lines_sublayer = f"{layer_name}\\{lines_layer_name}"

        print(f"Extracting OD lines for scenario {i} → {output_csv}")

        with open(output_csv, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["OriginID", "DestinationID", cost_field_name])

            with arcpy.da.SearchCursor(lines_sublayer, ["OriginID", "DestinationID", cost_field_name]) as cursor:
                for row in cursor:
                    writer.writerow(row)

        print(f"Scenario {i} completed. Saved to: {output_csv}")

    # Message indicating finish of OD-Cost Matrix calculations
    print(f"All {NUM_SIMULATIONS} scenarios processed successfully.")

except Exception as e:
    tb = traceback.format_exc()
    print("An error occurred:")
    print(tb)









