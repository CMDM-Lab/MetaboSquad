# The knowledge base is maintained separately, keeping tools and knowledge apart
ANALYSIS_KNOWLEDGE = {
  "one-factor-statistics":{
    "preprocessing": {
      "analysis": "preprocessing",
      "meaning": "Preprocessing: data object initialization, data integrity check, missing-value replacement and normalization.",
      "parameter_knowledge":{
          "paired": {
              "type": "boolean",
             "options": [
                {
                  "value": "FALSE",
                  "label": "Unpaired samples",
                  "description": "Standard independent-group design."
                },
                {
                  "value": "TRUE",
                  "label": "Paired samples",
                  "description": "Pre/post measurements on the same subjects, or a matched-pair design."
                }
              ],
              "default": "FALSE"
          },
          "format": {
              "type": "string",
              "options": [
                {
                  "value": "rowu",
                  "label": "Samples in rows, header on top",
                  "description": "Each row is one sample; the first row holds the feature names."
                },
                {
                  "value": "colu",
                  "label": "Samples in columns, header on the left",
                  "description": "Each column is one sample; the first column holds the feature names."
                },
                {
                  "value": "rowp",
                  "label": "Samples in rows, paired design",
                  "description": "Paired samples, with samples arranged in rows."
                },
                {
                  "value": "colp",
                  "label": "Samples in columns, paired design",
                  "description": "Paired samples, with samples arranged in columns."
                }
              ],
              "default": "rowu",
          },
          "label.type": {
              "type": "string",
              "options": [
                {
                  "value": "disc",
                  "label": "Discrete group labels",
                  "description": "Groups are a categorical variable, e.g. control / treatment."
                },
                {
                  "value": "cont",
                  "label": "Continuous labels",
                  "description": "Labels are numeric, e.g. a concentration gradient or a time series."
                }
              ],
              "default": "disc"
          },
          "rowNorm": {
              "type": "string",
              "display_name":"Sample normalization (between samples)",
              "options": [
                {
                  "value": "QuantileNorm",
                  "label": "Quantile normalization",
                  "description": "Makes the distributions of all samples identical; often used to handle strong batch effects."
                },
                {
                  "value": "ProbNormT",
                  "label": "Probabilistic quotient normalization (PQN, no reference)",
                  "description": "Use when samples differ by nonlinear dilution effects and no specific reference sample is available."
                },
                {
                  "value": "ProbNormF",
                  "label": "Probabilistic quotient normalization (PQN, reference-based)",
                  "description": "Use when a quality-control (QC) sample or an average sample is available as the reference."
                },
                {
                  "value": "CompNorm",
                  "label": "Normalization by a reference feature",
                  "description": "Use when an internal standard was added in the experiment."
                },
                {
                  "value": "SumNorm",
                  "label": "Normalization by sum",
                  "description": "The most basic correction; compensates for small differences in total concentration between samples."
                },
                {
                  "value": "MedianNorm",
                  "label": "Normalization by median",
                  "description": "Use when the data are expected to contain many extreme values, so the median is more representative than the mean."
                },
                {
                  "value": "SpecNorm",
                  "label": "Normalization by a sample-specific factor",
                  "description": "Use when a manual correction from experimental records (e.g. tissue weight, cell count) is needed."
                },
                {
                  "value": "NULL",
                  "label": "No sample normalization",
                  "description": "The data are already normalized."
                }
              ],
              "default": "NULL"
          },
          "transNorm": {
              "type": "string",
              "display_name":"Data transformation (corrects skewed distributions)",
              "options": [
                {
                  "value": "LogNorm",
                  "lable": "Log transformation",  
                  "description": "Use when the data are right-skewed (most metabolite data)"
                },
                {
                  "value": "CrNorm",
                  "lable": "Cube root transformation",
                  "description": "Use when the data contain many zeros, so a log transformation is not suitable"
                },
                {
                  "value": "NULL",
                  "lable": "No transformation",
                  "description": "The data are already close to a normal distribution"
                }
              ],
              "default": "LogNorm"
          },
          "scaleNorm": {
              "type": "string",
              "display_name":"Feature scaling (within features)",
              "options": [
                {
                  "value": "MeanCenter",
                  "label": "Mean centering",
                  "description": "Use when features have similar magnitudes; removes the offset and focuses on relative differences between samples."
                },
                {
                  "value": "AutoNorm",
                  "label": "Auto scaling (Z-score)",
                  "description": "Use when features differ greatly in magnitude and must be made comparable."
                },
                {
                  "value": "ParetoNorm",
                  "label": "Pareto Scaling",
                  "description": "Use to keep part of the magnitude information instead of full standardization."
                },
                {
                  "value": "RangeNorm",
                  "label": "Range Scaling (0-1)",
                  "description": "Use when all values must be mapped to the 0-1 range."
                },
                {
                  "value": "NULL",
                  "label": "No feature scaling",
                  "description": "Choose when another scaling step has already been applied."
                }
              ],
              "default": "AutoNorm"
          }   
        },
      "full_code": """
          library(MetaboAnalystR)

          # Initialize the data object
          mSet <- InitDataObjects("pktable", "stat", {paired})
          mSet <- Read.TextData(mSet, "{file_path}", "{format}", "{label.type}")

          # Data preprocessing
          mSet <- SanityCheckData(mSet)
          mSet <- ReplaceMin(mSet) # Replace missing/zero values with a small value
          mSet <- PreparePrenormData(mSet)
          # Normalization
          mSet <- Normalization(mSet, "{rowNorm}", "{transNorm}", "{scaleNorm}", ratio=FALSE, ratioNum=20)

          # Plots comparing data before and after normalization
          mSet <- PlotNormSummary(mSet, "norm_0_", "png", 300, width=NA)
          mSet <- PlotSampleNormSummary(mSet, "snorm_0_", "png", 300, width=NA)
          """
    },
    "pca": {
      "analysis": "PCA",
      "meaning": "Reduces dimensionality to show the overall differences between samples and to detect outliers.",
      "parameter_knowledge": {},
      "full_code": """
        # PCA plots
        mSet <- PCA.Anal(mSet)

        # Overview: pairwise scatter-plot matrix of the first 5 principal components
        mSet <- PlotPCAPairSummary(
            mSet,
            "pca_pair_0_",
            format  = "png",
            dpi     = 300,    
            width   = NA,    
            5                 # Show the first 5 principal components
        )

        # Scree plot: decide how many principal components to keep (find the elbow)
        mSet <- PlotPCAScree(mSet, "pca_scree_0_", "png", 300, width=NA, 5)

        # 2D score plot: sample distribution and clustering on PC1 vs PC2
        mSet <- PlotPCA2DScore(
            mSet,
            "pca_score2d_0_",
            format     = "png",
            dpi        = 300,
            width      = NA,
            1,                 # X axis: PC1 (explains the most variance)
            2,                 # Y axis: PC2
            0.95,              # 95% confidence ellipse, helps judge group separation
            1,                 # Show sample names (0 = hide)
            0                  # Use color (1 = grayscale, for black-and-white printing)
        )

        # Loading plot: direction and size of each feature's contribution to the components
        mSet <- PlotPCALoading(mSet, "pca_loading_0_", "png", 300, width=NA, 1, 2)

        # Biplot: sample distribution and feature contribution vectors together
        mSet <- PlotPCABiplot(mSet, "pca_biplot_0_", "png", 300, width=NA, 1, 2)
          """
    },
    "fold-change": {
      "analysis": "fold-change",
      "meaning": "Computes the fold change of each feature between two groups, to quickly screen for biologically relevant differential metabolites",
      "parameter_knowledge":{ 
          "paired": {
            "type": "boolean",
            "options": [
                {
                  "value": "FALSE",
                  "label": "Unpaired samples",
                  "description": "Standard independent-group design."
                },
                {
                  "value": "TRUE",
                  "label": "Paired samples",
                  "description": "Pre/post measurements on the same subjects, or a matched-pair design."
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """
        # Fold change analysis
        mSet <- FC.Anal(
            mSet,
            fc.thresh = 2.0,    # Fold change threshold: fold change > 2 counts as a significant difference
            cmp.type  = 0,      # 0 = group 1 - group 2
            {paired}
        )
        mSet <- PlotFC(mSet, "fc_0_", "png", 300, width=NA)
        """
    },
    "t-test": {
      "analysis": "t-test",
      "meaning": "Tests whether the mean of each feature differs significantly between two groups",
      "parameter_knowledge":{
          "paired": {
            "type": "boolean",
            "options": [
                {
                  "value": "FALSE",
                  "label": "Unpaired samples",
                  "description": "Standard independent-group design."
                },
                {
                  "value": "TRUE",
                  "label": "Paired samples",
                  "description": "Pre/post measurements on the same subjects, or a matched-pair design."
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """

        # t-test analysis
        mSet <- Ttests.Anal(
            mSet,
            nonpar   = FALSE,    # FALSE = parametric t-test (normalized data are close to normal)
                                 # TRUE  = non-parametric test (for very small sample sizes)
            threshp  = 0.05,     # adjusted p-value (FDR) cutoff
            paired   = {paired}, # paired or not
            equal.var= TRUE,     # TRUE = assume equal variances (Student's t-test)
                                 # FALSE = do not assume equal variances (Welch's t-test, usually more conservative)
            "fdr",               # multiple-testing correction for the significance cutoff
            FALSE                # FALSE = output only the significant metabolites
        )
        mSet <- PlotTT(mSet, "tt_0_", "png", 300, width=NA)
        """
    },
    "volcano": {
      "analysis": "volcano",
      "meaning": "Shows fold change and statistical significance together, to highlight the most important differential features",
      "parameter_knowledge":{
          "paired": {
            "type": "boolean",
            "options": [
                {
                  "value": "FALSE",
                  "label": "Unpaired samples",
                  "description": "Standard independent-group design."
                },
                {
                  "value": "TRUE",
                  "label": "Paired samples",
                  "description": "Pre/post measurements on the same subjects, or a matched-pair design."
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """
        # Volcano plot analysis
        mSet <- Volcano.Anal(
            mSet, 
            {paired},  # paired or not
            2.0,       # Fold change threshold: fold change > 2 counts as a significant difference
            0,         # 0 = group 1 vs group 2
            F,         # FALSE = parametric t-test (normalized data are close to normal)
            0.05,      # p-value threshold
            TRUE,      # TRUE = assume equal variances (Student's t-test)
            "fdr"      # "raw" for raw p-values, or "fdr"
        )
        mSet <- PlotVolcano(mSet, "volcano_0_", 1, 0, format ="png", dpi=300, width=NA)
        """
    },
    "anova": {
      "analysis": "anova",
      "meaning": "Tests whether there are significant differences among three or more groups",
      "parameter_knowledge":{ 
        },
      "full_code": """
        # ANOVA
        mSet <- ANOVA.Anal(
          mSet, 
          F,      # FALSE = parametric t-test (normalized data are close to normal)
          0.05,   # p-value threshold
          FALSE   # FALSE = output only the significant metabolites
        )
        mSet <- PlotANOVA(mSet, "aov_0_", "png", 300, width=NA)
        """
    },
    "pls-da": {
      "analysis": "pls-da",
      "meaning": "A supervised analysis that maximizes the differences between groups to find marker features (biomarkers)",
      "parameter_knowledge":{ 
        },
      "full_code": """
        # PLS-DA plots
        mSet <- PLSR.Anal(mSet) 

        # Score plots: PLS-DA classification performance
        mSet <- PlotPLSPairSummary(mSet, "pls_pair_0_", "png", 300, width=NA, 5)
        mSet <- PlotPLS2DScore(
            mSet,
            "pls_score2d_0_",
            format     = "png",
            dpi        = 300,
            width      = NA,
            1,    # latent variable 1
            2,    # latent variable 2
            0.95,
            1,
            0
        )
        mSet<-PlotPLS3DScoreImg(mSet, "pls_score3d_0_", "png", 300, width=NA, 1,2,3, 40)
        mSet<-PlotPLSLoading(mSet, "pls_loading_0_", "png", 300, width=NA, 1, 2)

        # Cross-validation (CV)
        mSet<-PLSDA.CV(mSet)
        mSet<-PlotPLS.Classification(mSet, "pls_cv_0_", "png", 300, width=NA)
        mSet<-PlotPLS.Imp(mSet, "pls_imp_0_", "png", 300, width=NA, "vip", "Comp. 1", 15, FALSE) # "vip": VIp scores,"type": coefficients

        # Permutation test
        mSet <- PLSDA.Permut(mSet, 100, "accu")
        mSet <- PlotPLS.Permutation(mSet, "pls_perm_0_", "png", 300, width=NA)
        """
    },
    "correlation_heatmap": {
      "analysis": "correlation_heatmap",
      "meaning": "Correlation heatmap",
      "parameter_knowledge":{ 
          "paired": {
            "type": "string",
            "options": [
                {
                  "value": "row",
                  "label": "features",
                  "description": "Correlation analysis between metabolites (features)"
                },
                {
                  "value": "col",
                  "label": "samples",
                  "description": "Correlation analysis between samples"
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """
        mSet<-PlotCorrHeatMap(
          mSet, 
          "corr_0_",   # image name 
          "png", 
          300, 
          width=NA, 
          "col",       # what to correlate: "row": features, "col": samples
          "pearson",   # method: 'pearson', 'spearman', or 'kendall'
          "bwm",       # colors: "bwm": default, "gbr": red/green, "heat": heat colors, "topo": topo colors, "gray": gray scale.
          TRUE,        # fix colors
          TRUE,        # clustered
          0.3,         # correlation coefficient cutoff
          "overview"   # "overview" or "detail" of the heatmap
        )
        """
    },
    "clustering": {
      "analysis": "clustering",
      "meaning": "Clustering analysis (hierarchical clustering, heatmap, K-means, SOM)",
      "parameter_knowledge":{ 
        },
      "full_code": """
        mSet<-PlotHCTree(
          mSet, 
          "tree_0_", 
          format = "png", 
          dpi=300, 
          width=NA, 
          "euclidean", # distance measure: euclidean, pearson, spearman
          "ward.D"     # clustering algorithm: average, complete, single
        )
        # Perform hierarchical clustering and plot heat map
        mSet<-PlotHeatMap(mSet, "heatmap_0_", "png", 300, width=NA, "norm", "row", "euclidean", "ward.D","bwm")

        # Perform K-means analysis
        mSet<-Kmeans.Anal(mSet, 3) # 3: number of clusters 
        mSet<-PlotKmeans(mSet, "km_0_", format = "png", dpi=300, width=NA)

        # Perform SOM analysis
        mSet<-SOM.Anal(mSet, 1, 3,"linear","gaussian")
        mSet<-PlotSOM(mSet, "som_0_", format = "png", dpi=72, width=NA)
        """
    },
    "random-forest": {
      "analysis": "random-forest",
      "meaning": "Random forest classification",
      "parameter_knowledge":{ 
        },
      "full_code": """
        mSet<-RF.Anal(mSet) 

        # Plot random forest classification
        mSet<-PlotRF.Classify(mSet, "rf_cls_0_", format = "png", dpi=300, width=NA)

        # Plot random forest variables of importance
        mSet<-PlotRF.VIP(mSet, "rf_imp_0_", format = "png", dpi=300, width=NA)

        # Plot random forest outliers 
        mSet<-PlotRF.Outlier(mSet, "rf_outlier_0_", format = "png", dpi=300, width=NA)
        """
    },
    "SVM": {
      "analysis": "support vector machine",
      "meaning": "Support vector machine (SVM) classification",
      "parameter_knowledge":{ 
        },
      "full_code": """
        # Perform SVM 
        mSet<-RSVM.Anal(mSet, 10)

        mSet<-PlotRSVM.Classification(mSet, "svm_cls_0_", format = "png", dpi=300, width=NA)

        mSet<-PlotRSVM.Cmpd(mSet, "svm_imp_0_", format = "png", dpi=300, width=NA)
        """
    },
  },
}