from shapely.geometry import Point, LineString
from shapely.ops import split


def make_connector_edges(
    edge_template,
    u_osmid,
    v_osmid,
    u_geom,
    v_geom,
    name
):
    """
    Create bidirectional connector edges between two nodes.

    Returns:
        - edge_out: Dictionary representing the outgoing connector edge
        - edge_in: Dictionary representing the incoming connector edge
    """

    line_out = LineString([u_geom, v_geom])
    line_in = LineString([v_geom, u_geom])

    base = edge_template.to_dict()

    base.update({
        "osmid": None,
        "highway": "unclassified",
        "name": name,
        "oneway": False,
        "length": line_out.length,
    })

    edge_out = {
        **base,
        "u": u_osmid,
        "v": v_osmid,
        "reversed": False,
        "geometry": line_out,
    }

    edge_in = {
        **base,
        "u": v_osmid,
        "v": u_osmid,
        "reversed": True,
        "geometry": line_in,
    }

    return edge_out, edge_in


def make_split_edges(
    nearest_edge,
    projected_osmid,
    line1,
    line2
):
    """
    Create replacement edges after splitting an existing edge.

    Returns:
        - e1_out: Dictionary representing the first outgoing edge
        - e1_in: Dictionary representing the first incoming edge
        - e2_out: Dictionary representing the second outgoing edge
        - e2_in: Dictionary representing the second incoming edge
    """

    base = nearest_edge.to_dict()

    u_orig = nearest_edge["u"]
    v_orig = nearest_edge["v"]

    e1_out = {
        **base,
        "u": u_orig,
        "v": projected_osmid,
        "reversed": False,
        "osmid": str(nearest_edge["osmid"]) + "_1_out",
        "length": line1.length,
        "geometry": line1,
    }

    e1_in = {
        **base,
        "u": projected_osmid,
        "v": u_orig,
        "reversed": True,
        "osmid": str(nearest_edge["osmid"]) + "_1_in",
        "length": line1.length,
        "geometry": LineString(list(line1.coords)[::-1]),
    }

    e2_out = {
        **base,
        "u": projected_osmid,
        "v": v_orig,
        "reversed": False,
        "osmid": str(nearest_edge["osmid"]) + "_2_out",
        "length": line2.length,
        "geometry": line2,
    }

    e2_in = {
        **base,
        "u": v_orig,
        "v": projected_osmid,
        "reversed": True,
        "osmid": str(nearest_edge["osmid"]) + "_2_in",
        "length": line2.length,
        "geometry": LineString(list(line2.coords)[::-1]),
    }

    return e1_out, e1_in, e2_out, e2_in

def append_edges(edge_gdf, *edges):

    for edge in edges:
        edge_gdf.loc[len(edge_gdf)] = edge


def drop_original_edge(edge_gdf, u_orig, v_orig):
    """
    Remove original edge pair after splitting.
    """

    idx = edge_gdf[
        ((edge_gdf["u"] == u_orig) & (edge_gdf["v"] == v_orig))
        | ((edge_gdf["u"] == v_orig) & (edge_gdf["v"] == u_orig))
    ].index.tolist()

    edge_gdf.drop(index=idx, inplace=True)
    edge_gdf.reset_index(drop=True, inplace=True)


def process_single_poi(
    row,
    edge_gdf,
    node_gdf,
    poi_id_col,
    tolerance,
):
    """
    Connect a single POI to the network.

    Two cases:
        - If POI projection on the edge: split nearest edge into two parts
        - If POI projection on the edge's node: connect POI to edge's node

    Returns:
        - edge_gdf: GeoDataFrame
        - node_gdf: GeoDataFrame
    """

    edge_index = edge_gdf.sindex

    poi_geom = row.geometry
    poi_osmid = row[poi_id_col]
    poi_name = row["name"]

    node_gdf.loc[len(node_gdf)] = {
        "osmid": poi_osmid,
        "y": poi_geom.y,
        "x": poi_geom.x,
        "junction": None,
        "street_count": None,
        "highway": None,
        "ref": "POI",
        "geometry": poi_geom,
    }

    nearest_idx = edge_index.nearest(
        poi_geom,
        return_all=False
    )[1][0]

    nearest_edge = edge_gdf.iloc[nearest_idx]
    edge_geom = nearest_edge.geometry

    projected_poi_geom = edge_geom.interpolate(
        edge_geom.project(poi_geom)
    )

    start_point = Point(edge_geom.coords[0])
    end_point = Point(edge_geom.coords[-1])

    split_required = True

    if projected_poi_geom.distance(start_point) < tolerance:

        projection_node_id = nearest_edge["u"]

        projection_node_geom = node_gdf.loc[
            node_gdf["osmid"] == projection_node_id,
            "geometry"
        ].values[0]

        split_required = False

    elif projected_poi_geom.distance(end_point) < tolerance:

        projection_node_id = nearest_edge["v"]

        projection_node_geom = node_gdf.loc[
            node_gdf["osmid"] == projection_node_id,
            "geometry"
        ].values[0]

        split_required = False

    if not split_required:

        edge_out, edge_in = make_connector_edges(
            edge_template=nearest_edge,
            u_osmid=poi_osmid,
            v_osmid=projection_node_id,
            u_geom=poi_geom,
            v_geom=projection_node_geom,
            name=f"{poi_name}_connector",
        )

        append_edges(edge_gdf, edge_out, edge_in)

    else:

        dx = projected_poi_geom.x - poi_geom.x
        dy = projected_poi_geom.y - poi_geom.y

        splitter_line = LineString([
            (poi_geom.x, poi_geom.y),
            (poi_geom.x + 2 * dx, poi_geom.y + 2 * dy)
        ])

        split_result = list(
            split(edge_geom, splitter_line).geoms
        )

        line1, line2 = split_result[0], split_result[1]

        projected_poi_geom = Point(line2.coords[0])
        projected_osmid = poi_osmid + 100000

        node_gdf.loc[len(node_gdf)] = {
            "osmid": projected_osmid,
            "y": projected_poi_geom.y,
            "x": projected_poi_geom.x,
            "junction": None,
            "street_count": None,
            "highway": None,
            "ref": poi_osmid,
            "geometry": projected_poi_geom,
        }

        u_orig = nearest_edge["u"]
        v_orig = nearest_edge["v"]

        append_edges(
            edge_gdf,
            *make_split_edges(
                nearest_edge,
                projected_osmid,
                line1,
                line2,
            )
        )

        drop_original_edge(
            edge_gdf,
            u_orig,
            v_orig,
        )

        edge_out, edge_in = make_connector_edges(
            edge_template=nearest_edge,
            u_osmid=poi_osmid,
            v_osmid=projected_osmid,
            u_geom=poi_geom,
            v_geom=projected_poi_geom,
            name=f"{poi_name}_connector",
        )

        append_edges(edge_gdf, edge_out, edge_in)

    return edge_gdf, node_gdf


def merge_poi_graph(
    poi_gdf,
    edge_gdf,
    node_gdf,
    poi_id_col,
    tolerance=0.01,
):
    """
    Merge all POIs into the road network.

    Returns:
    - edge_gdf: GeoDataFrame
    - node_gdf: GeoDataFrame
    """

    for _, row in poi_gdf.iterrows():

        edge_gdf, node_gdf = process_single_poi(
            row=row,
            edge_gdf=edge_gdf,
            node_gdf=node_gdf,
            poi_id_col=poi_id_col,
            tolerance=tolerance,
        )

    return edge_gdf, node_gdf