"""
SLMRND Optimization (LHS or MC)
--------------------------------
Solves a multi-scenario SLMRND model in Gurobi. 
Uses either LHS or MC input data for the given DISTRICT_NAME.

No functional changes, only path and file naming logic adapted.
"""

import csv
import os
import gurobipy as gp
from gurobipy import GRB
from itertools import combinations

# User Parameters
method = "MC"            # or "MC"
DISTRICT_NAME = "KADIKÖY" # e.g. "KADIKÖY"
scenario_count = 2      # total scenarios
subset_size = 2           # combination subset (e.g., 10C3)

district_name_lower = DISTRICT_NAME.lower()

# Identify directories
script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)

# Input subfolders
scenario_folder = f"{method}_Building_Selection"
node_subfolder = f"{method.lower()}_LDC_POD_DemandPoint_csv"
v0_subfolder = f"{method.lower()}_LDC-POD_Matrices"
v_subfolder = f"{method.lower()}_POD-DemandPoint_Matrices"

node_file_paths = {}
v0_file_paths = {}
v_file_paths = {}

# Build input paths
for i in range(1, scenario_count + 1):
    node_file_paths[i] = os.path.join(
        base_dir, "Building_Selection", scenario_folder, node_subfolder,
        f"{method}_LDC_POD_DemandPoint_{district_name_lower}_Scenario_{i}.csv"
    )
    v0_file_paths[i] = os.path.join(
        base_dir, "Gurobi_Optimization_SLMRND", "Input_Data_Files",
        f"{method.lower()}_input_files_gurobi", v0_subfolder,
        f"{method}_LDC-POD_Matrix_{district_name_lower}_Scenario_{i}.csv"
    )
    v_file_paths[i] = os.path.join(
        base_dir, "Gurobi_Optimization_SLMRND", "Input_Data_Files",
        f"{method.lower()}_input_files_gurobi", v_subfolder,
        f"{method}_POD-DemandPoint_Matrix_{district_name_lower}_Scenario_{i}.csv"
    )

# Output directory
output_dir = os.path.join(
    base_dir, "Gurobi_Optimization_SLMRND", "Output_Data_Files",
    f"{method.lower()}_output_files_gurobi"
)
os.makedirs(output_dir, exist_ok=True)

# Gap file name
gap_file_name = f"{method.lower()}_solution_gaps_{district_name_lower}_{scenario_count}c{subset_size}.csv"
gap_file = os.path.join(output_dir, gap_file_name)

# Write gap CSV header
with open(gap_file, 'w', newline='') as file:
    gap_writer = csv.writer(file)
    gap_writer.writerow(["Scenario_Combination", "Objective_Value", "Optimality_Gap"])

scenario_combinations = combinations(range(1, scenario_count + 1), subset_size)

# Import the SLMRNDData class (unmodified)
from SLMRNDData import SLMRNDData

import math

# Loop over scenario subsets
for combo in scenario_combinations:
    node_paths = {s: node_file_paths[s] for s in combo}
    v0_paths = {s: v0_file_paths[s] for s in combo}
    v_paths = {s: v_file_paths[s] for s in combo}
    
    data = SLMRNDData(node_paths, v0_paths, v_paths)
    
    data.check_v0_structure(1)
    data.check_v_structure(1)
    
    I, J, S = data.I, data.J, data.S
    p, d, v0, v = data.p, data.d, data.v0, data.v
    C, O_max, K = data.C, data.O_max, data.K
    epsilon, tau, rho = 0, 0, 0.4

    o = {s: min(O_max[s], sum(d.get((s, i), 0) for i in I)) for s in S}

    model = gp.Model("SLMRND")

    y = model.addVars(J, vtype=GRB.BINARY, name="y")
    R = model.addVars(J, vtype=GRB.CONTINUOUS, name="R")
    x = model.addVars(S, I, J, vtype=GRB.BINARY, name="x")
    r = model.addVars(S, J, vtype=GRB.CONTINUOUS, name="r")
    beta = model.addVars(S, J, vtype=GRB.CONTINUOUS, name="beta")

    TD = {(j, s): gp.quicksum(x[s, i, j] * d.get((s, i), 0) for i in I) for j in J for s in S}

    PD = {}
    for j in J:
        for s in S:
            total_dem = sum(d.get((s, i), 0) for i in I)
            PD[(j, s)] = (o[s] / total_dem) * TD[(j, s)] if total_dem > 0 else 0

    eta = gp.quicksum(p[s] * gp.quicksum(v0.get(s, {}).get(j, 0)*y[j] for j in J) for s in S)
    Q = gp.quicksum(p[s] * (gp.quicksum(v.get(s, {}).get(i, {}).get(j, 0)*x[s, i, j] for i in I for j in J)
               - epsilon*gp.quicksum(beta[s, j] for j in J)) for s in S)
    model.setObjective(eta + Q, GRB.MAXIMIZE)

    model.addConstrs((gp.quicksum(y[j] for j in J) <= C for s in S), "max_PODs")
    model.addConstrs((R[j] <= K[j]*y[j] for j in J), "capacity")
    model.addConstrs((r[s, j] <= R[j] for j in J for s in S), "delivery_capacity")
    model.addConstrs((gp.quicksum(r[s, j] for j in J) == o[s] for s in S), "total_supplies")
    model.addConstrs((gp.quicksum(x[s, i, j] for j in J) == 1 for i in I for s in S), "demand_served")
    model.addConstrs((x[s, i, j] <= y[j] for i in I for j in J for s in S), "serve_opened_only")
    model.addConstrs((x[s, j, j] >= y[j] for j in J for s in S), "open_POD_serves_itself")
    model.addConstrs((r[s, j] <= PD[j, s] + beta[s, j] for j in J for s in S), "proportional_demand_upper")
    model.addConstrs((PD[j, s] + beta[s, j] <= TD[j, s] for j in J for s in S), "proportional_demand_with_beta")
    model.addConstrs((TD[j, s] - r[s, j] <= rho*TD[j, s] for j in J for s in S), "deviation_limit")
    model.addConstrs((r[s, j] >= 0 for j in J for s in S), "non_negativity_r")
    model.addConstrs((beta[s, j] >= 0 for j in J for s in S), "non_negativity_beta")
    model.addConstrs((R[j] >= 0 for j in J), "non_negativity_R")

    model.setParam('TimeLimit', 10)
    model.optimize()

    scenario_str = "_".join(map(str, combo))

    if model.SolCount > 0:
        try:
            y_sol = model.getAttr('x', y)
            R_sol = model.getAttr('x', R)
            x_sol = model.getAttr('x', x)

            print(f"{method} Objective value for {combo}: {model.ObjVal}")

            y_file = os.path.join(output_dir, f"{method}_{district_name_lower}_y_solution_scenarios_{scenario_str}.csv")
            R_file = os.path.join(output_dir, f"{method}_{district_name_lower}_R_solution_scenarios_{scenario_str}.csv")
            x_file = os.path.join(output_dir, f"{method}_{district_name_lower}_x_solution_scenarios_{scenario_str}.csv")

            with open(y_file, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["POD", "y_value"])
                for j, val in y_sol.items():
                    writer.writerow([j, val])

            with open(R_file, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["POD", "R_value"])
                for j, val in R_sol.items():
                    writer.writerow([j, val])

            with open(x_file, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Scenario", "Demand_Node", "POD", "x_value"])
                for (s, i, j), val in x_sol.items():
                    writer.writerow([s, i, j, val])

        except gp.GurobiError as e:
            print(f"Error retrieving solution: {e}")
    else:
        print("No feasible solution found in time limit.")

    if model.status in [GRB.OPTIMAL, GRB.TIME_LIMIT]:
        gap = model.MIPGap if model.status == GRB.TIME_LIMIT else 0
        obj_val = model.ObjVal if model.status == GRB.OPTIMAL else "N/A"
        with open(gap_file, 'a', newline='') as file:
            gap_writer = csv.writer(file)
            gap_writer.writerow([scenario_str, obj_val, gap])
        print(f"{method} Scenarios {scenario_str}: Obj = {obj_val}, Gap = {gap}")

print("Optimization complete.")

