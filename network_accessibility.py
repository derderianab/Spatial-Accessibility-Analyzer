import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from shapely.geometry import box


def get_administrative_boundary(
        city_name,
        target_crs
):
    """
    Get administrative boundary of project area to create and filter grids outside the boundary.

    Return:
        - boundary_gdf: GeoDataFrame
    """

    boundary_gdf = ox.geocode_to_gdf(
        city_name
    )

    boundary_gdf = boundary_gdf.to_crs(
        target_crs
    )

    return boundary_gdf


def build_graph(
        nodes_gdf,
        edges_gdf
):
    """
    Initiate network graph for accessibility analysis using merged nodes and edges.

    Return:
        - graph G: OSMNX Graph
    """

    G = nx.Graph()

    for _, row in nodes_gdf.iterrows():

        G.add_node(
            row["osmid"]
        )

    for _, row in edges_gdf.iterrows():

        G.add_edge(
            row["u"],
            row["v"],
            weight=row["length"]
        )

    return G


def calculate_node_accessibility(
        G,
        nodes_gdf,
        pois_gdf,
        cat_name,
        pois_id,
        weights
):
    """
    Calculates Accessibility Index in each node.

    Return:
        - nodes_gdf (with accessibility index): GeoDataFrame
    """

    nodes_gdf = nodes_gdf.copy()

    ### Calculate distance to nearest POI for each node
    for amenity in pois_gdf[cat_name].dropna().unique():

        source_nodes = pois_gdf.loc[
            pois_gdf[cat_name] == amenity,
            pois_id
        ].tolist()

        distances = nx.multi_source_dijkstra_path_length(
            G,
            source_nodes,
            weight="weight"
        )

        nodes_gdf[f"{amenity}_dist"] = (
            nodes_gdf["osmid"]
            .map(distances)
        )

    ### Normalize node to POI distance using global values
    criteria_dist = []
    for i in weights.keys():
        col = i + "_dist"
        criteria_dist.append(col)

    max_distance_global = []
    for col in criteria_dist:
        max_distance_global.append(nodes_gdf[col].max())
    max_distance_global = round(max(max_distance_global),3)

    for col in criteria_dist:
        nodes_gdf[f"{col}_norm"] = (
            1 - (nodes_gdf[col] / max_distance_global)
        )

    ### Calculate node accessibility index using normalized distances and AHP weights
    nodes_gdf["accessibility_index"] = 0
    for amenity, weight in weights.items():
        nodes_gdf["accessibility_index"] += (
            nodes_gdf[f"{amenity}_dist_norm"]
            * weight
        )

    return nodes_gdf


def generate_grid(
        boundary_gdf,
        grid_size
):
    """
    Initiate grids as container to visualize accessibility index.

    Return:
        - grid_gdf: GeoDataFrame
    """


    minx, miny, maxx, maxy = (
        boundary_gdf.total_bounds
    )

    grid_cells = [

        box(
            x,
            y,
            x + grid_size,
            y + grid_size
        )

        for x in np.arange(
            minx,
            maxx,
            grid_size
        )

        for y in np.arange(
            miny,
            maxy,
            grid_size
        )

    ]

    grid_gdf = gpd.GeoDataFrame(
        geometry=grid_cells,
        crs=boundary_gdf.crs
    )

    grid_gdf["grid_id"] = range(
        len(grid_gdf)
    )

    selected_idx = gpd.sjoin(
        grid_gdf,
        boundary_gdf,
        predicate="intersects"
    ).index.unique()

    grid_gdf = grid_gdf.loc[
        selected_idx
    ].copy()

    return grid_gdf


def aggregate_to_grid(
        nodes_gdf,
        grid_gdf
):
    """
    Aggregate node accessibility indices to grid cells using the median value.

    Return:
        - grid_gdf (with aggregated nodes accessibility index): GeoDataFrame
    """

    joined = gpd.sjoin(
        nodes_gdf,
        grid_gdf,
        how="left",
        predicate="within"
    )

    grid_stats = (
        joined
        .groupby("grid_id")
        .agg(
            accessibility_index=(
                "accessibility_index",
                "median"
            ),
            node_count=(
                "osmid",
                "count"
            )
        )
        .reset_index()
    )

    grid_gdf = grid_gdf.merge(
        grid_stats,
        on="grid_id",
        how="left"
    )

    return grid_gdf


# =============================================================================
# GAP FILLING
# =============================================================================

def gap_fill_grid(
        grid_gdf,
        grid_size
):
    """
    Fill missing accessibility indices for grid cells that contain no nodes.

    Returns:
        - grid_gdf (with missing accessibility values filled): GeoDataFrame
    """

    grid_gdf = grid_gdf.copy()

    grid_gdf["cx"] = (
        grid_gdf.geometry.centroid.x
    )

    grid_gdf["cy"] = (
        grid_gdf.geometry.centroid.y
    )

    grid_gdf["col"] = (
        (
            grid_gdf["cx"]
            - grid_gdf["cx"].min()
        )
        / grid_size
    ).round().astype(int)

    grid_gdf["row"] = (
        (
            grid_gdf["cy"]
            - grid_gdf["cy"].min()
        )
        / grid_size
    ).round().astype(int)

    lookup = {

        (
            row["row"],
            row["col"]
        ): idx

        for idx, row
        in grid_gdf.iterrows()

    }

    iteration = 0

    while True:

        iteration += 1

        updates = {}

        nan_idx = grid_gdf[
            grid_gdf[
                "accessibility_index"
            ].isna()
        ].index

        for idx in nan_idx:

            r = grid_gdf.loc[
                idx,
                "row"
            ]

            c = grid_gdf.loc[
                idx,
                "col"
            ]

            neighbor_values = []

            for dr in [-1, 0, 1]:

                for dc in [-1, 0, 1]:

                    if dr == 0 and dc == 0:
                        continue

                    neighbor_idx = lookup.get(
                        (
                            r + dr,
                            c + dc
                        )
                    )

                    if neighbor_idx is None:
                        continue

                    value = grid_gdf.loc[
                        neighbor_idx,
                        "accessibility_index"
                    ]

                    if not np.isnan(value):

                        neighbor_values.append(
                            value
                        )

            if neighbor_values:

                updates[idx] = np.median(
                    neighbor_values
                )

        for idx, value in updates.items():

            grid_gdf.loc[
                idx,
                "accessibility_index"
            ] = value

        print(
            f"Iteration {iteration}: "
            f"filled {len(updates)} grids"
        )

        if len(updates) == 0:
            break

    print(
        "Remaining NaN:",
        grid_gdf[
            "accessibility_index"
        ].isna().sum()
    )

    grid_gdf = grid_gdf.drop(
        columns=[
            "cx",
            "cy",
            "row",
            "col"
        ]
    )

    return grid_gdf


def run_accessibility_analysis(
        city_name,
        nodes_gdf,
        edges_gdf,
        pois_gdf,
        cat_name,
        pois_id,
        weights,
        grid_size=250
):
    """
    Run the complete network-based accessibility analysis workflow.

    Returns:
    - boundary_gdf: GeoDataFrame
    - nodes_gdf: GeoDataFrame
    - grid_gdf: GeoDataFrame
    """

    ### Initiating boundary
    boundary_gdf = (
        get_administrative_boundary(
            city_name,
            nodes_gdf.crs
        )
    )

    ### Building network graph
    G = build_graph(
        nodes_gdf,
        edges_gdf
    )

    ### Calculating node accessibility
    print("\nCalculating node accessibility...")

    nodes_gdf = (
        calculate_node_accessibility(
            G,
            nodes_gdf,
            pois_gdf,
            cat_name,
            pois_id,
            weights
        )
    )

    ### Generating grid
    print("\nGenerating grid...")

    grid_gdf = generate_grid(
        boundary_gdf,
        grid_size
    )

    ### Calculating accessibility index for each grid
    print("\nAggregating to grid...")

    grid_gdf = aggregate_to_grid(
        nodes_gdf,
        grid_gdf
    )

    ### Calculating accessibility index for grids with no nodes
    print("\nGap filling...")

    grid_gdf = gap_fill_grid(
        grid_gdf,
        grid_size
    )

    return (
        boundary_gdf,
        nodes_gdf,
        grid_gdf
    )