# harmonise.py
# Builds districts with the same boundaries in May 1928, Sept 1930 and July 1932.
#
# Idea: when a Kreis changed, ZA8013 keeps the old and new versions as separate
# rows and links them with Haenisch's keys (each key value is the row_id of the
# row it combines with). I treat every Kreis as a node in a graph, add an edge
# for every key that links two Kreise, and each connected group of Kreise
# becomes one stable unit.
#
# Small changes (e.g. one village moving to the next Kreis) would otherwise force
# big merges, so like Haenisch I ignore a link if both Kreise carry on with
# a population change under 10% (1928-30) or 20% (1930-32).
#
# Run: python harmonise.py out          (reads the CSVs from extract.py)
#      python harmonise.py out strict   (follow every link instead)

import sys
import os
import networkx as nx
import numpy as np
import pandas as pd

YEARS = ["1928", "1930", "1932j"]
TOL_28_30 = 0.10
TOL_30_32 = 0.20


def stable_kreise(kreise, year_a, year_b, tol):
    """Kreise that have results in both years and barely changed in population."""
    in_both = kreise["nsdap_" + year_a].notna() & kreise["nsdap_" + year_b].notna()
    change = abs(kreise["pop_" + year_b] / kreise["pop_" + year_a] - 1)
    return set(kreise.loc[in_both & (change <= tol), "kreis_id"])


def add_links(graph, rows, key_col, kreis_of_row, skip=None):
    """Add an edge between each row's Kreis and the Kreis its key points to."""
    added = 0
    for kreis_id, key in zip(rows["kreis_id"], rows[key_col]):
        if key == 0:
            continue
        other = kreis_of_row[key]
        if other == kreis_id:
            continue
        if skip and kreis_id in skip and other in skip:
            continue  # both carry on fine on their own
        graph.add_edge(kreis_id, other)
        added += 1
    return added


def share(rows, group_col, num, den):
    """Sum numerator and denominator per group, then divide (only rows with both)."""
    rows = rows[rows[num].notna() & rows[den].notna()]
    totals = rows.groupby(group_col)[[num, den]].sum()
    return totals[num] / totals[den], totals[den]


def main():
    out_dir = sys.argv[1]
    strict = len(sys.argv) > 2 and sys.argv[2] == "strict"

    kreise = pd.read_csv(os.path.join(out_dir, "kreis_raw.csv"))
    munis = pd.read_csv(os.path.join(out_dir, "municipal_raw.csv"))

    # ---------- 1. group linked Kreise ----------
    graph = nx.Graph()
    graph.add_nodes_from(kreise["kreis_id"])

    skip_28_30 = None if strict else stable_kreise(kreise, "1928", "1930", TOL_28_30)
    skip_30_32 = None if strict else stable_kreise(kreise, "1930", "1932j", TOL_30_32)

    # 1928-30 key is at municipal level: a municipality pointing into another
    # Kreis means land moved between those Kreise
    links_28_30 = add_links(graph, munis, "key_1928_1930",
                            dict(zip(munis["row_id"], munis["kreis_id"])), skip_28_30)
    links_30_32 = add_links(graph, kreise, "key_1930_1932",
                            dict(zip(kreise["row_id"], kreise["kreis_id"])), skip_30_32)

    # only keep groups that have results in at least one of my elections
    has_data = kreise[[f"nsdap_{y}" for y in YEARS]].notna().any(axis=1)
    active = set(kreise.loc[has_data, "kreis_id"])

    unit_of = {}
    unit_id = 0
    groups = sorted(nx.connected_components(graph), key=min)
    for group in groups:
        if group & active:
            unit_id += 1
            for k in group:
                unit_of[k] = unit_id
    kreise["unit_id"] = kreise["kreis_id"].map(unit_of).astype("Int64")  # Int64 allows blanks

    # a second, wider grouping that also follows the Nov 1932 and 1933 keys.
    # Some census figures sit on these later versions (e.g. after the Prussian
    # reform of 1 Oct 1932), so I fall back to them for census shares.
    wide = graph.copy()
    kreis_of_row = dict(zip(kreise["row_id"], kreise["kreis_id"]))
    add_links(wide, kreise, "key_1932_1932", kreis_of_row)
    add_links(wide, kreise, "key_1932_1933", kreis_of_row)
    wide_of = {}
    for i, group in enumerate(nx.connected_components(wide)):
        for k in group:
            wide_of[k] = i
    kreise["wide_id"] = kreise["kreis_id"].map(wide_of)
    kreise["region"] = kreise["wahlkreis"].astype(str) + "-" + kreise["regbez"].astype(str)

    # ---------- 2. add up the votes per unit ----------
    k = kreise[kreise["unit_id"].notna()]
    by_unit = k.groupby("unit_id")

    units = pd.DataFrame({
        "name": by_unit["name"].apply(lambda names: " + ".join(dict.fromkeys(names))),
        "wahlkreis": by_unit["wahlkreis"].first(),
        "n_records": by_unit.size(),
        "kreis_ids": by_unit["kreis_id"].apply(lambda ids: " ".join(map(str, sorted(ids)))),
    })

    for y in YEARS:
        voted = k[k["nsdap_" + y].notna()].groupby("unit_id")
        for col in ["eligible", "valid", "nsdap", "pop"]:
            units[f"{col}_{y}"] = voted[f"{col}_{y}"].sum()
        units["nsdap_share_" + y] = units["nsdap_" + y] / units["valid_" + y]
        units["nsdap_share_eligible_" + y] = units["nsdap_" + y] / units["eligible_" + y]

    # ---------- 3. census shares ----------
    # use the unit's own figures if it has them, then the wider unit, then the region
    first_wide = by_unit["wide_id"].first()
    first_region = by_unit["region"].first()

    def census(name, num, den):
        own, own_den = share(k, "unit_id", num, den)
        wider, _ = share(kreise, "wide_id", num, den)
        region, _ = share(kreise, "region", num, den)

        own = units.index.map(own)
        wider = first_wide.map(wider)
        region = first_region.map(region)

        units[name] = pd.Series(own, index=units.index).fillna(wider).fillna(region)
        units[name + "_source"] = np.select(
            [pd.notna(own), wider.notna(), region.notna()],
            ["own", "wider unit", "region"], default="missing")
        return units.index.map(own_den)

    religion_pop = census("catholic_share", "c25_catholic", "c25_pop")
    census("protestant_share", "c25_protestant", "c25_pop")
    occupation_pop = census("agri_share", "c25_agri", "c25_occ_total")
    census("unemp_rate_1933", "c33_unemployed", "c33_active")

    # how much of the unit's population its own census figures cover (1 = exact)
    units["religion_coverage"] = religion_pop / units["pop_1928"]
    units["occupation_coverage"] = occupation_pop / units["pop_1928"]

    # ---------- 4. checks ----------
    units["pop_change_28_30"] = abs(units["pop_1930"] / units["pop_1928"] - 1)
    units["pop_change_30_32"] = abs(units["pop_1932j"] / units["pop_1930"] - 1)
    units["complete"] = units[[f"nsdap_{y}" for y in YEARS]].notna().all(axis=1)

    not_own = (units[["catholic_share_source", "agri_share_source",
                      "unemp_rate_1933_source"]] != "own").any(axis=1)
    bad_cover = ~(units["religion_coverage"].between(0.9, 1.1)
                  & units["occupation_coverage"].between(0.9, 1.1))
    units["census_approx"] = not_own | bad_cover

    units.index.name = "unit_id"
    units.to_csv(os.path.join(out_dir, "units.csv"))

    lookup = kreise[["row_id", "kreis_id", "name", "level", "wahlkreis", "unit_id"]]
    lookup.sort_values(["unit_id", "row_id"]).to_csv(os.path.join(out_dir, "lookup.csv"), index=False)

    # ---------- 5. report ----------
    lines = []
    lines.append(f"Mode: {'strict' if strict else 'tolerance (10% / 20%)'}")
    lines.append(f"Links used: 1928-30 {links_28_30}, 1930-32 {links_30_32}")
    lines.append(f"Units: {len(units)} (complete in all 3 elections: {units['complete'].sum()})")
    lines.append(f"  single record: {(units['n_records'] == 1).sum()}, "
                 f"several records: {(units['n_records'] > 1).sum()}")
    lines.append("")

    published = {"1928": 2.6, "1930": 18.3, "1932j": 37.4}
    lines.append("NSDAP % of valid votes (published):")
    for y in YEARS:
        mine = 100 * units["nsdap_" + y].sum() / units["valid_" + y].sum()
        covered = units["valid_" + y].sum() / kreise["valid_" + y].sum()
        lines.append(f"  {y}: {mine:.1f}% ({published[y]}%), valid votes covered {covered:.1%}")
    lines.append("")

    big = units.nlargest(10, "n_records")
    lines.append("Biggest units:")
    for uid, row in big.iterrows():
        lines.append(f"  {uid}: {row['n_records']} records, pop {row['pop_1930']:,.0f} - {row['name'][:90]}")
    lines.append("")

    lines.append(f"Population change over tolerance: "
                 f"{((units['pop_change_28_30'] > TOL_28_30) | (units['pop_change_30_32'] > TOL_30_32)).sum()}")
    for col in ["catholic_share", "agri_share", "unemp_rate_1933"]:
        counts = units[col + "_source"].value_counts()
        lines.append(f"{col} source: " + ", ".join(f"{s} {n}" for s, n in counts.items()))
    lines.append(f"Units with approximate census values: {units['census_approx'].sum()}")
    lines.append("")
    lines.append("Approximate units:")
    approx = units[units["census_approx"]]
    for uid, row in approx.iterrows():
        lines.append(f"  {uid}: {row['name'][:50]:50s} religion {row['catholic_share_source']:10s} "
                     f"({row['religion_coverage']:.2f})  agri {row['agri_share_source']:10s} "
                     f"({row['occupation_coverage']:.2f})  unemp {row['unemp_rate_1933_source']}")

    report = "\n".join(lines)
    with open(os.path.join(out_dir, "report.txt"), "w") as f:
        f.write(report)
    print("\n".join(lines[:20]))


if __name__ == "__main__":
    main()