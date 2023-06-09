import os
from matplotlib import pyplot as plt
import scanpy as sc
from differential_expression_analysis import Differential_Expression_Analysis as dea

#Set scanpy settings, turned figure settings off for now
sc.settings.verbosity = 3             # verbosity: errors (0), warnings (1), info (2), hints (3)
sc.logging.print_header()
sc.settings.set_figure_params(dpi=150, facecolor='white')


# TO DO: store doublet as layer? if we remove doublets as a filtering step BEFORE PCA,
# We won't be able to plot the clustering plot, but if we leave it in, they will be present
# in the sample integration. --> try out layer or remove umap plot. (umap plot requires leidenalg)

# Might've solved this problem with adata itself as input for dea. idk why I didn't think of this sooner
# Look into way to do this without error.
# but use adata.raw.to_adata() for dea plots! Otherwise it wont find them

class Sample_Analysis:

    # Init that sets variables, calls create_AnnData() method and runs all code below with run() method
    def __init__(self, sample_dir, sample_name, output_dir, markerpath):
        self.sample_dir = sample_dir
        self.sample_name = sample_name
        self.output_dir = output_dir
        self.full_path = os.path.join(self.sample_dir, self.sample_name, 'filtered_feature_bc_matrix')
        self.sample_output = os.path.join(self.output_dir, self.sample_name)
        self.adata = self.create_AnnData()
        self.markerpath = markerpath
        self.run()


    # Create master folder/sub folder structure
    def create_folders(self):
        os.makedirs(self.sample_output)
        os.chdir(self.sample_output)
        os.makedirs('QC')
        os.makedirs('PCA')
        os.makedirs('DEA')
        os.makedirs('Clusters')
        os.makedirs('AnnData_storage')

    
    # Create AnnData oject, store in cache for faster future access
    def create_AnnData(self):
        print(f'Creation of {self.sample_name} AnnData object pending...')
        return sc.read_10x_mtx(path=self.full_path, var_names='gene_symbols', cache=True)


    # filter_cells and calculate qc based on mitochondrial RNA 
    def calculate_qc(self):
        sc.pp.filter_cells(self.adata, min_genes=700)   # Keep cells with at least 700 genes expressed
        sc.pp.filter_genes(self.adata, min_cells=3)     # Keep genes that are expressed in atleast 3 cells
        self.adata.uns[self.sample_name] = self.sample_name
        self.adata.var['mt'] = self.adata.var_names.str.startswith('MT-')    # Filter out MT- RNA
        sc.pp.calculate_qc_metrics(self.adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)
        

    # Save QC plots to correct folders    
    def create_QC_plots(self):    
        sc.pl.violin(self.adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'], 
                     scale='width', color='#9ADCFF', multi_panel=True, show=False)
        plt.savefig(os.path.join(self.sample_output, 'QC', 'QC_nfeatn_count_percMT_'+self.sample_name+'.png'))
        sc.pl.scatter(self.adata, 'pct_counts_mt', 'total_counts', color='pct_counts_mt',
                      title='Percentage of MT RNA in counts '+self.sample_name, color_map='Blues', show=False)
        plt.savefig(os.path.join(self.sample_output, 'QC', 'Pct_MT_RNA_in_counts'+self.sample_name+'.png'))
        sc.pl.scatter(self.adata, 'n_genes_by_counts', 'total_counts', color='n_genes_by_counts',
                      title='Amount of genes by counts '+self.sample_name, color_map='Blues', show=False)
        plt.savefig(os.path.join(self.sample_output, 'QC', 'ngenes_by_counts'+self.sample_name+'.png'))


    # Detect doublets in dataset
    def detect_doublets(self):
        sc.external.pp.scrublet(self.adata, adata_sim=None, batch_key=None, sim_doublet_ratio=2.0, expected_doublet_rate=0.06, stdev_doublet_rate=0.02, synthetic_doublet_umi_subsampling=1.0, knn_dist_metric='euclidean',
                         normalize_variance=True, log_transform=False, mean_center=True, n_prin_comps=30, use_approx_neighbors=True, get_doublet_neighbor_parents=False, n_neighbors=None, threshold=None,
                           verbose=True, copy=False, random_state=0) # auto-set threshold. Do not manually generate doublets.
        sc.external.pl.scrublet_score_distribution(self.adata, show=False)
        plt.savefig(os.path.join(self.sample_output, 'QC', 'doublet_score_distribution_'+self.sample_name+'.png'))
        self.adata.obs['doublet_info'] = self.adata.obs["predicted_doublet"].astype(str)


    # Subset, Regress out bad stuff and normalize, find variablefeatures and do some other stuff like SCTransform
    def normalization_HVG(self):
        self.adata = self.adata[self.adata.obs.pct_counts_mt < 20, :] # EDIT 24-4-2023: slice away MT- counts that are too high
        self.detect_doublets()
        sc.pp.normalize_total(self.adata, target_sum=1e4) # EDIT: removed this: still included highly expressed data for now
        sc.pp.log1p(self.adata)
        sc.pp.highly_variable_genes(self.adata, flavor='cell_ranger', subset=False) # EDIT: added this line for testing
        sc.pl.highly_variable_genes(self.adata, show=False)
        plt.savefig(os.path.join(self.sample_output, 'QC', 'Highly_variable_genes_'+self.sample_name+'.png'))
        # better to remove doublets before calling raw data as last filtering step
        #self.adata = self.adata[self.adata.obs['doublet_info'] == 'False',:]
        self.adata.raw = self.adata
        self.adata = self.adata[:, self.adata.var.highly_variable] # Actually do the slicing
        sc.pp.regress_out(self.adata, ['total_counts', 'pct_counts_mt']) # regress out sequencing depth and % MT-RNA
        sc.pp.scale(self.adata)


    # Run a PCA and plot output
    def run_PCA(self):
        sc.tl.pca(self.adata, n_comps=50)       # Create 50 components
        #self.adata.write(os.path.join(self.sample_output, 'AnnData_storage', 'PCA_'+self.sample_name+'.h5ad'))
        sc.pl.pca(self.adata, annotate_var_explained=True, na_color='#9ADCFF', title=f'PCA scoringsplot {self.sample_name}', show=False)
        plt.savefig(os.path.join(self.sample_output, 'PCA', 'PCA_Scores_'+self.sample_name+'.png'))
        sc.pl.pca_loadings(self.adata, components=[1,2], show=False) # Only show first 2.
        plt.savefig(os.path.join(self.sample_output, 'PCA', 'PCA_loadings_plot_'+self.sample_name+'.png'))
        sc.pl.pca_variance_ratio(self.adata, n_pcs=19, show=False)
        plt.savefig(os.path.join(self.sample_output, 'PCA', 'PCA_Variance_elbow_'+self.sample_name+'.png'))


    # Perform unsupervised clustering on the un-annotated sample
    def unsupervised_clustering(self):
        sc.pp.neighbors(self.adata, n_neighbors=10, n_pcs=20) # calculate neighbors with 20 npc's
        sc.tl.umap(self.adata)
        sc.tl.leiden(self.adata, resolution=0.5)      # resolution default for scanpy = 1. resolution used in seurat = 0.5.
        title=f'Unsupervised Leiden Cluster {self.sample_name}'
        sc.pl.umap(self.adata, color=['leiden'], title=title, legend_loc='on data', legend_fontsize=8, show=False)
        plt.savefig(os.path.join(self.sample_output, 'Clusters', 'Unsupervised_UMAP_'+self.sample_name+'.png'))
        sc.pl.umap(self.adata, color=['doublet_score', 'doublet_info'], show=False)
        plt.savefig(os.path.join(self.sample_output, 'Clusters', 'Doublet_umap'+self.sample_name+'.png'))
        # remove doublets here? 
        # write anndata object to h5ad file



    # run all functions at once and write AnnData
    def run(self):
        self.create_folders()
        self.calculate_qc()
        self.create_QC_plots() 
        self.normalization_HVG()
        df_obs = sc.get.obs_df(self.adata, ['n_genes', 'n_genes_by_counts', 'total_counts', 'total_counts_mt', 'pct_counts_mt'])
        df_vars = sc.get.var_df(self.adata, ['gene_ids', 'feature_types', 'n_cells', 'mt', 'n_cells_by_counts', 'mean_counts', 'pct_dropout_by_counts', 'total_counts', 'highly_variable', 'means', 'dispersions', 'dispersions_norm'])
        df_obs.to_csv(self.sample_output+'/adata_obs', sep='\t', encoding='utf-8')
        df_vars.to_csv(self.sample_output+'/adata_vars', sep='\t', encoding='utf-8')
        self.run_PCA()
        self.unsupervised_clustering()
        # remove doublets as a final step
        # Q maurits: do this earlier because this is technically pre-processing
        # the consequence of this is no UMAP plot after clustering with the doublets shown
        # what is the better option?
        self.adata = self.adata[self.adata.obs['doublet_info'] == 'False',:]
        self.adata_DE = self.adata.raw.to_adata()
        deado = dea(self.adata_DE, self.sample_output, self.sample_name, self.markerpath)
        deado.perform_dea()
        deado.basic_dea_plots()
        self.adata.write(os.path.join(self.sample_output, 'AnnData_storage', self.sample_name+'.h5ad'))
