from argparse import ArgumentParser
import os
import sys
import numpy as np
import h5py
import json
from calc_marker_genes_helpers import calc_marker_genes_error_bars_approx2, calc_marker_genes_single, \
    calc_marker_genes_double
import pandas as pd

if __name__ == '__main__':
    parent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    # Add the parent directory of this script-file to sys.path
    sys.path.append(parent_dir)
    os.chdir(parent_dir)

    from bonsai.bonsai_helpers import str2bool
    from bonsai_scout.bonsai_scout_helpers import Bonvis_metadata

    parser = ArgumentParser(
        description='This script calculates marker features that best distinguish two groups of leaves in the '
                    'Bonsai-tree. The .json-file should contain:'
                    '- feature_path: address in the bonsai_vis_data.hdf to feature data for which we want to get the markers'
                    '- cell_ids_group1: list of cell-ids in first group'
                    '- cell_ids_group2: similarly'
                    'This json-file can be generated by selecting the desired subgroups in the "Marker genes"-pane of '
                    'Bonsai-scout, and clicking the "Download marker groups"-button.')

    parser.add_argument('--marker_groups_json', type=str, default='marker_groups_info.json',
                        help='Path to the json-file described above.')
    parser.add_argument('--marker_output_file', type=str, default='',
                        help='Absolute path to where the output should be stored. If left empty, it is stored in '
                             'the Bonsai-results folder under name "output_marker_script.tsv"')
    parser.add_argument('--results_folder', type=str, default=None,
                        help='Absolute (or relative to "bonsai-development") path to bonsai results folder that'
                             'contains the files created by vis_bonsai_preprocess: bonsai_vis_settings.json and'
                             'bonsai_vis_data.hdf')
    parser.add_argument('--settings_filename', type=str, default='bonsai_vis_settings.json',
                        help='Filename of json-file that contains app settings. This file should be present in the '
                             'results_folder. Note that new json-files are created when one clicks "Store settings"'
                             'in the app.')

    args = parser.parse_args()

    bonsai_data_path = os.path.abspath(os.path.join(args.results_folder, 'bonsai_vis_data.hdf'))
    bonsai_vis_settings_path = os.path.abspath(os.path.join(args.results_folder, args.settings_filename))

    bonvis_metadata = Bonvis_metadata(bonsai_data_path)
    bonvis_data_hdf = h5py.File(bonsai_data_path, 'r')

    with open(args.marker_groups_json, 'r') as file:
        marker_groups_info = json.load(file)

    cell_ids_group1 = marker_groups_info['cell_ids_group1']
    cell_ids_group2 = marker_groups_info['cell_ids_group2']
    feature_path = marker_groups_info['feature_path']

    feature_hdf = bonvis_data_hdf[feature_path]
    run_with_vars = 'yes' if ('vars' in feature_hdf.keys()) else 'no'

    # Get cell inds
    node_ids_features = json.loads(feature_hdf.attrs['node_ids'])
    node_id_to_ind = {node_id: ind for ind, node_id in enumerate(node_ids_features)}
    cell_inds_group1 = [node_id_to_ind[node_id] for node_id in cell_ids_group1]
    cell_inds_group2 = [node_id_to_ind[node_id] for node_id in cell_ids_group2]

    if run_with_vars == 'yes':
        print("Calculating marker genes accounting for the error-bars "
              "between groups of sizes {} and {}.".format(len(cell_inds_group1), len(cell_inds_group2)))

        n_points = 300
        means = feature_hdf['means']
        vars = feature_hdf['vars']
        gene_ids = json.loads(feature_hdf.attrs['gene_ids'])
        cells_wo_nan = np.where(np.sum(np.isnan(means), axis=0) == 0)[0]
        ds_cell_inds_1 = np.intersect1d(cell_inds_group1, cells_wo_nan)
        ds_cell_inds_2 = np.intersect1d(cell_inds_group2, cells_wo_nan)

        marker_genes = calc_marker_genes_error_bars_approx2(indices1=ds_cell_inds_1, indices2=ds_cell_inds_2,
                                                            means=means,
                                                            vars=vars, gene_ids=gene_ids, n_points_total=n_points,
                                                            n_marker_genes=None)

    else:
        # Note that we only get ranks for cells that have no nan-value for any gene
        ranks_per_gene = feature_hdf['ranks_per_gene']
        cells_wo_nan = np.where(np.sum(ranks_per_gene == -1, axis=0) == 0)[0]
        n_cells = len(cells_wo_nan)
        ds_cell_inds_1 = np.intersect1d(cell_inds_group1, cells_wo_nan)
        ds_cell_inds_2 = np.intersect1d(cell_inds_group2, cells_wo_nan)

        gene_ids = json.loads(feature_hdf.attrs['gene_ids'])
        variation_features = np.setdiff1d(np.arange(len(gene_ids)), feature_hdf['no_variation_features'])

        if len(ds_cell_inds_2) == 0:
            marker_genes = calc_marker_genes_single(ds_cell_inds_1, n_cells, gene_ids, ranks_per_gene,
                                                    n_marker_genes=10,
                                                    gene_subset=variation_features)
        else:
            ds_cell_inds_2 = np.intersect1d(ds_cell_inds_2, cells_wo_nan)
            marker_genes = calc_marker_genes_double(ds_cell_inds_1, ds_cell_inds_2, n_cells, gene_ids,
                                                    ranks_per_gene,
                                                    n_marker_genes=10,
                                                    gene_subset=variation_features)

    # Do the postprocessing to store the marker genes in a tsv file
    marker_genes_df = pd.DataFrame.from_dict(marker_genes, orient='index', columns=['marker_scores'])
    marker_genes_df.reset_index(inplace=True)
    marker_genes_df.rename({'marker_scores': 'marker_scores', 'index': 'marker_genes'}, axis=1,
                           inplace=True)
    marker_scores = marker_genes_df['marker_scores'].values
    sorted_markers = np.argsort(np.minimum(marker_scores, 1 - marker_scores))
    marker_genes_df = marker_genes_df.iloc[sorted_markers]

    if len(args.marker_output_file) == 0:
        args.marker_output_file = os.path.join(args.results_folder, 'output_marker_script.tsv')
    marker_genes_df.to_csv(args.marker_output_file, sep='\t')
