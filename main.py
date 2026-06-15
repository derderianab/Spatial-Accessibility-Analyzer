from network_accessibility import run_accessibility_analysis
from merge_poi_graph import merge_poi_graph
from ahp_process import run_ahp

import sys
import osmnx as ox
import geopandas as gpd


### User Input
PLACE = input("Enter project area name (e.g., Kota Bandung, Indonesia): ") # Name of the project area used to retrieve the road network from OpenStreetMap.
POI_FILE_NAME = input("Enter POI file name with extension (located in the data folder): ") # Name of the POI file located in the data folder.
POI_CAT_COL_NAME = input("Enter POI category column name: ") # Name of the column containing POI categories (e.g., hospital, fire station, police).
POI_CONN_ID_COL_NAME = input("Enter POI unique ID column name: ") # Name of the unique identifier column used to connect POIs to the network.
OUTPUT_NAME = input("Enter output file name (without extension): ") # Name of the output accessibility grid file to be saved in the output folder.
INPUT_CRS_CODE  = str(input("Enter projected CRS EPSG code (e.g., 32748): ")) # Projected coordinate reference system (CRS) used for all spatial analyses.

POI_DIR = f"data/{POI_FILE_NAME}"
OUTPUT_FILE_NAME = OUTPUT_NAME + ".gpkg"
OUTPUT_DIR  = f"output/{OUTPUT_FILE_NAME}"
NETWORK_CRS = f"EPSG:{INPUT_CRS_CODE}"

pois = gpd.read_file(POI_DIR)
pois = pois.to_crs(NETWORK_CRS)

criteria = (
    pois[POI_CAT_COL_NAME]
    .dropna()
    .unique()
    .tolist()
)


### Criteria Weight Determination
if len(criteria) == 1:
    criteria_weights = {
        criteria[0] : 1
    }

else:
    print("Starting AHP pairwise comparison...")

    ahp_result = run_ahp(pois, amenity_col=POI_CAT_COL_NAME)
    criteria_weights = ahp_result["weights"]
    consistency_ratio = round(ahp_result["consistency_ratio"],3)

    print("\nAHP pairwise comparison results")
    print("Weights: ",criteria_weights)
    print("Consistency ratio: ",consistency_ratio)

    if consistency_ratio < 0.1:
        #print(f"\nConsistency Ratio = {consistency_ratio:.4f}")
        print("The pairwise comparisons are consistent.")
        print("\nContinue analyzing....")
    else:
        #print(f"\nConsistency Ratio = {consistency_ratio:.4f}")
        print("The pairwise comparisons are inconsistent.")
        print("\nPlease review your judgments.")
        sys.exit()


### Retrieve Network
print("\nDownloading graph from OSM...")

G = ox.graph_from_place(PLACE, network_type="drive")
nodes, edges = ox.graph_to_gdfs(G)

nodes = nodes.reset_index()
edges = edges.reset_index()

nodes = nodes.to_crs(NETWORK_CRS)
edges = edges.to_crs(NETWORK_CRS)


### Merge Poi and Graph
print("\nIntegrating POIs and graph node...")

merged_edges_gdf, merged_nodes_gdf = merge_poi_graph(
    pois,
    edges,
    nodes,
    poi_id_col=POI_CONN_ID_COL_NAME,
    tolerance=0.01, # Min Distance of POI to Edge's Node (To Classify POI as Edge's Node)
)

merged_edges_gdf = merged_edges_gdf.set_crs(NETWORK_CRS)
merged_nodes_gdf = merged_nodes_gdf.set_crs(NETWORK_CRS)


### Run Accessibility Analysis
boundary_gdf, result_nodes_gdf, result_grid_gdf = run_accessibility_analysis(
        PLACE,
        merged_nodes_gdf,
        merged_edges_gdf,
        pois,
        POI_CAT_COL_NAME,
    POI_CONN_ID_COL_NAME,
        criteria_weights,
        grid_size=250
)


### Save grid
result_grid_gdf.to_file(
    OUTPUT_DIR,
    driver="GPKG"
)

print(f"\nGrid saved to {OUTPUT_DIR}")
