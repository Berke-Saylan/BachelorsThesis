"""
This single Python module processes scenario-based input data (nodes, v0, and v 
matrices) for the 2 stage stochastic optimization model based on SLMRND model from
Balcik et al. 2016. The input data preparation for the gurobi python optimization
is the same for Latin Hypercube Sampling (LHS) or Monte Carlo (MC) scenario generations.

Usage:
1. Create a dictionary of file paths for each scenario: 
   - `node_file_paths[s]` 
   - `v0_file_paths[s]` 
   - `v_file_paths[s]`
   for scenario index `s`.
2. Instantiate the class:

    data = SLMRNDData(
        node_file_paths=node_file_paths,
        v0_file_paths=v0_file_paths,
        v_file_paths=v_file_paths,
        method='MC'  # or 'LHS')

    Parameters:
    node_file_paths : dict
        Dictionary keyed by scenario indices, each value is a CSV file path 
        containing demand data (nodes) for that scenario.
    v0_file_paths : dict
        Dictionary keyed by scenario indices, each value is a CSV file path 
        for the v0 matrix (LDC → POD accessibility).
    v_file_paths : dict
        Dictionary keyed by scenario indices, each value is a CSV file path 
        for the v matrix (POD → demand point accessibility).
    method : str, optional
        Either "LHS" or "MC" to distinguish the scenario approach; no 
        functional difference is made here by default, but you can insert 
        conditional checks if needed.

    Attributes:
    S : list
        Sorted list of scenario indices.
    p : dict
        Probability of each scenario (defaults to uniform).
    nodes : pd.DataFrame
        Node data from the first scenario file, used to define columns 
        like 'Area' and 'Demand'.
    I : list
        Demand node IDs (1 to 950).
    J : list
        Candidate POD IDs (1 to 173).
    C : int
        Maximum number of PODs to open.
    d : dict
        Demands keyed by (scenario, node ID).
    v0 : dict
        LDC→POD accessibility data, keyed by scenario.
    v : dict
        POD→demand accessibility data, keyed by scenario.
    O_max : dict
        Maximum supplies for each scenario (sum of demands).
    K : dict
        Capacity upper bound for each POD, possibly shifted so that 
        POD ID = 1 is set to zero capacity.
    tau : float
        Threshold parameter (if used) for coverage-based analyses.
    method : str
        Stores the "LHS" or "MC" string.

3. The class will:
   - Parse node data, compute demands, define sets, 
   - Load v0 and v matrices (accessibility scores),
   - Optionally normalize times to a [0, 1] range,
   - Calculate capacities, 
   - Provide additional utility methods to check or export data structures.
   
Notes:
    - The user must ensure that the CSV files contain columns named:
      'Area', 'Demand', 'OriginID', 'DestinationID', 'Total_TruckingDuration'.
    - The capacity calculation (`calculate_capacity_upper_bound`) uses 
      node areas to distribute total supplies proportionally.
    - If method='MC' vs. method='LHS' requires changes in future 
      logic, add if-statements inside this class.
"""

import pandas as pd
import numpy as np
import math as math

class SLMRNDData:
    def __init__(self, node_file_paths, v0_file_paths, v_file_paths, method='LHS'):
        # Keep track of which method we're using, if needed for future customization
        self.method = method

        # Original constructor logic
        self.S = sorted(node_file_paths.keys())  # List of scenario indices
        self.p = {s: 1 / len(self.S) for s in self.S}  # Equal probability for each scenario

        # Load node data from the first scenario to define the 'nodes' DataFrame
        first_scenario = self.S[0]
        self.nodes = self.load_and_process_nodes(node_file_paths[first_scenario])

        # Define sets
        self.I = list(range(1, 951))  # Demand nodes
        self.J = list(range(1, 174))  # Candidate PODs
        self.C = 100  # Max number of PODs to open

        # Initialize data structures
        self.d = {}      # Demand at node i under scenario s
        self.v0 = {}     # Accessibility from LDC to POD
        self.v = {}      # Accessibility from POD to demand node
        self.O_max = {}  # Total supplies under scenario s

        # Replace null 'Area' with 0
        self.nodes['Area'] = self.nodes['Area'].fillna(0)

        # Load scenario-specific data
        for s in self.S:
            # Load demands for scenario s
            nodes_s = self.load_and_process_nodes(node_file_paths[s])
            demands_s = self.get_demands(nodes_s, s)
            self.d.update(demands_s)

            # Total supplies for scenario s = sum of demands
            self.O_max[s] = nodes_s['Demand'].sum()

            # Load v0 for scenario s
            self.v0[s] = self.load_v0_matrix(v0_file_paths[s])

            # Load v for scenario s
            self.v[s] = self.load_v_matrix(v_file_paths[s])

        # Calculate the capacity upper bound
        self.K = self.calculate_capacity_upper_bound()

        # If K is not empty, remove its last key-value pair
        # (as done in both separate classes)
        if self.K:
            last_key = list(self.K.keys())[-1]
            del self.K[last_key]

        self.tau = 0  # Default tau threshold
        
    """ 
    Finds the optimal tau that yields ~50% coverage for each POD.
    target_coverage : float: The desired fraction of demand nodes that should be "covered" (score >= tau) by each POD.
    tau_range : array-like: Sequence of tau values to test, e.g. np.linspace(0, 1, 100). 
    """
    def find_optimal_tau(self, target_coverage=0.5, tau_range=np.linspace(0, 1, 100)):
        deviations = {}

        for tau in tau_range:
            coverage_counts = {pod: 0 for pod in self.J}

            # Access each scenario's v data
            for (scenario, destination, origin), score in self.v.items():
                if score >= tau:
                    coverage_counts[origin] += 1

            total_demand_points = len(self.I)
            deviations[tau] = sum(
                abs((coverage_counts[pod] / total_demand_points) - target_coverage)
                for pod in self.J
            ) / len(self.J)

        # Return the tau that yields minimal coverage deviation
        optimal_tau = min(deviations, key=deviations.get)
        return optimal_tau

    # Load the node data (e.g., from CSV) and process columns, fill 0s instead of nulls
    def load_and_process_nodes(self, file_path):
        nodes = pd.read_csv(file_path, delimiter=',', decimal='.')
        nodes['Area'] = pd.to_numeric(nodes['Area'], errors='coerce')
        nodes['Demand'] = pd.to_numeric(nodes['Demand'], errors='coerce')
        nodes['Demand'].fillna(0, inplace=True)
        return nodes

    # Create a demand dictionary keyed by (scenario, nodeID).
    def get_demands(self, nodes, scenario):
        demands = nodes['Demand'].to_dict()
        return {(scenario, i + 1): demand for i, demand in demands.items()}
    
    
    """
    Calculate capacity upper bound for each POD, uses a proportional approach:
        - Sum the 'Area' for all candidate PODs (IDs in self.J).
        - Scale by max O_max across scenarios.
        - Multiply by 1.5 factor, is an empiric value, can be changed depending on desired outcome.
        - Distribute among PODs proportionally to each POD's area.
    """
    def calculate_capacity_upper_bound(self):
        pod_areas = self.nodes.loc[self.J, 'Area'].sum()
        if pod_areas == 0:
            raise ValueError("Total area for PODs is zero. Ensure PODs have valid area values.")

        max_o = max(self.O_max.values())
        self.nodes.loc[self.J, 'Capacity'] = (
            self.nodes.loc[self.J, 'Area'] * max_o * 1.5
        ) / pod_areas

        capacities = {1: 0}  # Set POD ID 1 capacity to 0
        capacities.update({
            index + 1: capacity
            for index, capacity in self.nodes.loc[self.J, 'Capacity'].items()
        })

        return capacities

    # Load and process the v0 matrix (LDC to POD) for one scenario.
    def load_v0_matrix(self, file_path_v0):
        v0_matrix = pd.read_csv(file_path_v0, delimiter=',', decimal='.')
        v0_matrix['Accessibility_Score'] = self.normalize_column(v0_matrix['Total_TruckingDuration'])

        # Initialize all PODs to an accessibility of 1 as a fallback
        v0_dict = {destination: 1 for destination in self.J}

        # Overwrite with the actual normalized values from the CSV
        for _, row in v0_matrix.iterrows():
            destination = row['DestinationID']
            score = row['Accessibility_Score']
            if destination in v0_dict:
                v0_dict[destination] = score

        return v0_dict

    # Load and process the v matrix (POD to demand points) for one scenario.
    def load_v_matrix(self, file_path_v):
        v_dict_scenario = {}
        v_matrix = pd.read_csv(file_path_v, delimiter=',', decimal='.')
        v_matrix['Accessibility_Score'] = self.normalize_column(v_matrix['Total_TruckingDuration'])

        for _, row in v_matrix.iterrows():
            origin = row['OriginID']
            destination = row['DestinationID']
            score = row['Accessibility_Score']

            if destination in self.I and origin in self.J:
                if destination not in v_dict_scenario:
                    v_dict_scenario[destination] = {}
                v_dict_scenario[destination][origin] = score

        return v_dict_scenario

    # Write the structure of the v matrix for scenario s to a text file for debugging
    def check_v_structure(self, s, output_file="v_structure_output_scenario.txt"):
        with open(output_file, "w") as file:
            if s in self.v:
                file.write(f"Scenario {s}:\n")
                for key, value in self.v[s].items():
                    file.write(f"{key} -> {value}\n")
            else:
                file.write(f"Scenario {s} not found in the v matrix.\n")

    # Write the structure of the v0 matrix for scenario s to a text file for debugging
    def check_v0_structure(self, s, output_file="v0_structure_output_scenario.txt"):
        with open(output_file, "w") as file:
            if s in self.v0:
                file.write(f"Scenario {s}:\n")
                for key, value in self.v0[s].items():
                    file.write(f"{key} -> {value}\n")
            else:
                file.write(f"Scenario {s} not found in the v0 matrix.\n")

    """
        Normalize a column of numerical values to range [0, 1], with higher raw
        trucking durations resulting in lower normalized values.
    """
    @staticmethod
    def normalize_column(column):
        min_val = column.min()
        max_val = column.max()
        if max_val == min_val:
            return column * 0
        return (max_val - column) / (max_val - min_val)

    # Flatten and export the v dictionary to a CSV file
    def export_v_dict(self, output_file):
        v_dict_flat = [
            [s, destination, origin, score]
            for (s, destination, origin), score in self.v.items()
        ]
        v_dict_df = pd.DataFrame(v_dict_flat, columns=['Scenario', 'DestinationID', 'OriginID', 'Accessibility_Score'])
        v_dict_df.to_csv(output_file, index=False, sep=';')

    # Print demands and capacities for a specified scenario to stdout
    def print_demands_and_capacities(self, scenario):
        print(f"Demands for Scenario {scenario}:")
        for node, demand in self.d.items():
            if node[0] == scenario:
                print(f"Node ID: {node[1]}, Demand: {demand}")

        print(f"\nCapacities for Scenario {scenario}:")
        for pod, capacity in self.K.items():
            print(f"POD ID: {pod}, Capacity: {capacity}")



