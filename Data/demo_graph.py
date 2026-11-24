
# CODE IS AI-ENHANCED (ChatGPT improvements + tests+ similarity comparison to the geographic graph)
import pandas as pd
import networkx as nx
from sklearn.neighbors import NearestNeighbors

DIR= "C://Users//gnisa//Documents//Third Year Project//Data//"
# Need to mess around with changing this value of k
K=5

#1. Load node data
nodes = pd.read_csv(DIR+ "nodes.csv")
nodes["node_id"]= nodes["node_id"].astype(int)
assert len(nodes)==749


# ADDITIONAL CHECKS: Node data
assert nodes["node_id"].is_unique, "Duplicate node IDs"
assert nodes["node_id"].notna().all(), "Missing node IDs"
assert nodes[["catholic_share", "agri_share"]].notna().all().all(), "Missing demographic features"
assert nodes[["catholic_share", "agri_share"]].apply(lambda col: col.between(0, 1).all()).all(), "Shares outside 0-1 range"
assert 0 < K < len(nodes), "Invalid value of K"


#2. Standardise the two features so both count equally
features= nodes[["catholic_share", "agri_share"]]
Z= (features - features.mean())/features.std()


# ADDITIONAL CHECKS: Standardisation
assert (features.std() > 0).all(), "A feature has zero variance"
assert Z.notna().all().all(), "Missing standardised values"


#3. For every district, find its k most similar districts
# K+1 because each district's nearest neighbour is itself

nn= NearestNeighbors(n_neighbors=K+1).fit(Z)
distances, indices= nn.kneighbors(Z)

ids=nodes["node_id"].tolist()
rows=[]

for i, target_id in enumerate(ids):
    neighbour_count=0

    for j, distance in zip(indices[i], distances[i]):
        #Skip the district itself
        if j==i:
            continue

        #Create an edge from the similar district to the target district
        source_id= ids[j]
        rows.append((source_id, target_id, distance))

        neighbour_count+=1

        #Stop once the k nearest neighbours have been added
        if neighbour_count==K:
            break
demo= pd.DataFrame(rows, columns=["source", "target", "feature_dist"])
demo["edge_type"]= "demographic"
demo["w_equal"]=1/K

# MAYBE ADD SOME CHECKS HERE??

# ADDITIONAL CHECKS: Demographic edges

# Exactly K incoming edges per district
assert len(demo) == len(nodes) * K, "Incorrect total edge count"

# No duplicate directed edges
assert not demo.duplicated(subset=["source", "target"]).any(), "Duplicate edges"

# No self-loops
assert (demo["source"] != demo["target"]).all(), "Self-loops found"

# Every district appears as a target
assert set(demo["target"]) == set(ids), "Some target districts are missing"

# All sources and targets are valid node IDs
assert set(demo["source"]).issubset(set(ids)), "Invalid source IDs"
assert set(demo["target"]).issubset(set(ids)), "Invalid target IDs"

# Every district has exactly K incoming neighbours
assert (demo.groupby("target").size() == K).all(), "Incorrect neighbours per district"

# Distances must be non-negative and non-missing
assert demo["feature_dist"].notna().all(), "Missing feature distances"
assert (demo["feature_dist"] >= 0).all(), "Negative feature distances"

# Incoming weights must sum to 1 for every district
assert ((demo.groupby("target")["w_equal"].sum() - 1).abs() < 1e-9).all(), "Weights do not sum to 1"

print("All demographic graph checks passed!")


G= nx.DiGraph()
G.add_nodes_from(ids)
G.add_edges_from(demo[["source", "target"]].itertuples(index=False, name=None))
print("Weakly connected components:", nx.number_weakly_connected_components(G))
print("Strongly connected components:", nx.number_strongly_connected_components(G))


# 4. Compare demographic graph with geographic graph

geo = pd.read_csv(DIR + "geographic_weights.csv")

# Check geographic graph data
assert {"source", "target"}.issubset(geo.columns), "Missing geographic edge columns"
assert geo[["source", "target"]].notna().all().all(), "Missing geographic endpoints"

geo["source"] = geo["source"].astype(int)
geo["target"] = geo["target"].astype(int)

assert not geo.duplicated(subset=["source", "target"]).any(), "Duplicate geographic edges"
assert set(geo["source"]).issubset(set(ids)), "Unknown geographic source IDs"
assert set(geo["target"]).issubset(set(ids)), "Unknown geographic target IDs"

# Build geographic graph
G_geo = nx.DiGraph()
G_geo.add_nodes_from(ids)
G_geo.add_edges_from(geo[["source", "target"]].itertuples(index=False, name=None))

# Compare graph statistics
print("\n--- GRAPH COMPARISON ---")

print("Demographic nodes:", G.number_of_nodes())
print("Geographic nodes:", G_geo.number_of_nodes())

print("Demographic edges:", G.number_of_edges())
print("Geographic edges:", G_geo.number_of_edges())

print("Demographic weak components:", nx.number_weakly_connected_components(G))
print("Geographic weak components:", nx.number_weakly_connected_components(G_geo))

print("Demographic strong components:", nx.number_strongly_connected_components(G))
print("Geographic strong components:", nx.number_strongly_connected_components(G_geo))

# Average incoming and outgoing neighbours
print("Demographic average in-degree:", sum(dict(G.in_degree()).values()) / len(ids))
print("Geographic average in-degree:", sum(dict(G_geo.in_degree()).values()) / len(ids))

print("Demographic average out-degree:", sum(dict(G.out_degree()).values()) / len(ids))
print("Geographic average out-degree:", sum(dict(G_geo.out_degree()).values()) / len(ids))

# Compare which directed edges are shared
demo_edges = set(G.edges())
geo_edges = set(G_geo.edges())

shared_edges = demo_edges & geo_edges
all_edges = demo_edges | geo_edges

print("\n--- EDGE OVERLAP ---")

print("Shared edges:", len(shared_edges))
print("Demographic-only edges:", len(demo_edges - geo_edges))
print("Geographic-only edges:", len(geo_edges - demo_edges))

print("Percentage of demographic edges also geographic:",
      round(100 * len(shared_edges) / len(demo_edges), 2), "%")

print("Jaccard similarity:",
      round(len(shared_edges) / len(all_edges), 4))
