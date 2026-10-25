# The knowledge base is maintained separately, keeping tools and knowledge apart
ANALYSIS_KNOWLEDGE = {
  "one-factor-statistics":{
    "preprocessing": {
      "analysis": "preprocessing",
      "meaning": "分析預處理包含數據物件初始化、。",
      "parameter_knowledge":{
          "paired": {
              "type": "boolean",
             "options": [
                {
                  "value": "FALSE",
                  "label": "非配對樣本",
                  "description": "一般獨立組別設計。"
                },
                {
                  "value": "TRUE",
                  "label": "配對樣本",
                  "description": "同一受試者的前後測或配對設計。"
                }
              ],
              "default": "FALSE"
          },
          "format": {
              "type": "string",
              "options": [
                {
                  "value": "rowu",
                  "label": "樣本在列，標頭在上方",
                  "description": "每一列代表一個樣本，第一行為特徵名稱。"
                },
                {
                  "value": "colu",
                  "label": "樣本在行，標頭在左方",
                  "description": "每一行代表一個樣本，第一列為特徵名稱。"
                },
                {
                  "value": "rowp",
                  "label": "樣本在列，配對設計",
                  "description": "配對樣本且樣本排列在列。"
                },
                {
                  "value": "colp",
                  "label": "樣本在行，配對設計",
                  "description": "配對樣本且樣本排列在行。"
                }
              ],
              "default": "rowu",
          },
          "label.type": {
              "type": "string",
              "options": [
                {
                  "value": "disc",
                  "label": "離散分組標籤",
                  "description": "分組為類別變數，如 control / treatment。"
                },
                {
                  "value": "cont",
                  "label": "連續型標籤",
                  "description": "標籤為數值，如濃度梯度、時間序列。"
                }
              ],
              "default": "disc"
          },
          "rowNorm": {
              "type": "string",
              "display_name":"樣本間正規化",
              "options": [
                {
                  "value": "QuantileNorm",
                  "label": "分位數正規化",
                  "description": "旨在使所有樣本的分佈一致，常用於處理顯著的批次效應。"
                },
                {
                  "value": "ProbNormT",
                  "label": "機率商正規化 (PQN, 無參考)",
                  "description": "當樣本間存在非線性稀釋差異，且無法提供特定參考樣本時。"
                },
                {
                  "value": "ProbNormF",
                  "label": "機率商正規化 (PQN, 基於參考)",
                  "description": "有明確的質控樣本 (QC) 或平均樣本作為基準時使用。"
                },
                {
                  "value": "CompNorm",
                  "label": "特定特徵正規化",
                  "description": "實驗中有加入內部對照品 (Internal Standard) 時使用。"
                },
                {
                  "value": "SumNorm",
                  "label": "總和正規化",
                  "description": "最基礎的校正，用於補償樣本間總體濃度的微小偏差。"
                },
                {
                  "value": "MedianNorm",
                  "label": "中位數正規化",
                  "description": "預期數據中存在較多極端值，中位數比平均值更具代表性時。"
                },
                {
                  "value": "SpecNorm",
                  "label": "樣本特定因子正規化",
                  "description": "需要根據實驗紀錄（如組織重量、細胞數量）進行手動校正時。"
                },
                {
                  "value": "NULL",
                  "label": "不做樣本間正規化",
                  "description": "資料已預先完成正規化。"
                }
              ],
              "default": "NULL"
          },
          "transNorm": {
              "type": "string",
              "display_name":"校正數據的偏態分佈",
              "options": [
                {
                  "value": "LogNorm",
                  "lable": "對數轉換",  
                  "description": "資料呈右偏分佈時使用（大多數代謝物數據）"
                },
                {
                  "value": "CrNorm",
                  "lable": "立方根轉換",
                  "description": "資料含大量零值，log 轉換不適用"
                },
                {
                  "value": "NULL",
                  "lable": "不做轉換",
                  "description": "資料已接近常態分佈"
                }
              ],
              "default": "LogNorm"
          },
          "scaleNorm": {
              "type": "string",
              "display_name":"樣本內特徵縮放",
              "options": [
                {
                  "value": "MeanCenter",
                  "label": "平均值中心化",
                  "description": "特徵數量級接近，旨在消除截距影響並專注於樣本間的相對差異。"
                },
                {
                  "value": "AutoNorm",
                  "label": "Z-score 標準化",
                  "description": "各特徵數量級差異大，需要可比性時使用。"
                },
                {
                  "value": "ParetoNorm",
                  "label": "Pareto Scaling",
                  "description": "想保留部分數量級資訊，不要完全標準化時使用。"
                },
                {
                  "value": "RangeNorm",
                  "label": "Range Scaling (0-1)",
                  "description": "需要將所有值映射到 0-1 範圍時使用。"
                },
                {
                  "value": "NULL",
                  "label": "不做特徵縮放",
                  "description": "已完成其他標準化處理時選擇。"
                }
              ],
              "default": "AutoNorm"
          }   
        },
      "full_code": """
          library(MetaboAnalystR)

          # 初始化數據物件
          mSet <- InitDataObjects("pktable", "stat", {paired})
          mSet <- Read.TextData(mSet, "{file_path}", "{format}", "{label.type}")

          # 數據預處理
          mSet <- SanityCheckData(mSet)
          mSet <- ReplaceMin(mSet) # 替換最小值
          mSet <- PreparePrenormData(mSet)
          # 標準化
          mSet <- Normalization(mSet, "{rowNorm}", "{transNorm}", "{scaleNorm}", ratio=FALSE, ratioNum=20)

          # 標準化前後比較圖
          mSet <- PlotNormSummary(mSet, "norm_0_", "png", 300, width=NA)
          mSet <- PlotSampleNormSummary(mSet, "snorm_0_", "png", 300, width=NA)
          """
    },
    "pca": {
      "analysis": "PCA",
      "meaning": "用於降低維度並觀察樣本間的整體差異與離群值。",
      "parameter_knowledge": {},
      "full_code": """
        # PCA 圖表輸出
        mSet <- PCA.Anal(mSet)

        # 綜覽圖：顯示前 5 個主成分的兩兩散點矩陣
        mSet <- PlotPCAPairSummary(
            mSet,
            "pca_pair_0_",
            format  = "png",
            dpi     = 300,    
            width   = NA,    
            5                 # 顯示前 5 個主成分
        )

        # Scree Plot：判斷應保留幾個主成分（找轉折點）
        mSet <- PlotPCAScree(mSet, "pca_scree_0_", "png", 300, width=NA, 5)

        # 2D Score Plot：觀察樣本在 PC1 vs PC2 的分佈與分群
        mSet <- PlotPCA2DScore(
            mSet,
            "pca_score2d_0_",
            format     = "png",
            dpi        = 300,
            width      = NA,
            1,                 # X 軸：第 1 主成分（解釋變異最大）
            2,                 # Y 軸：第 2 主成分
            0.95,              # 95% 信賴橢圓，協助判斷組別分離程度
            1,                 # 顯示樣本名稱（0=隱藏）
            0                  # 使用彩色（1=灰階，適合黑白印刷）
        )

        # Loading Plot：顯示各特徵對主成分的貢獻方向與強度
        mSet <- PlotPCALoading(mSet, "pca_loading_0_", "png", 300, width=NA, 1, 2)

        # Biplot：同時呈現樣本分佈與特徵貢獻向量
        mSet <- PlotPCABiplot(mSet, "pca_biplot_0_", "png", 300, width=NA, 1, 2)
          """
    },
    "fold-change": {
      "analysis": "fold-change",
      "meaning": "計算兩組間各特徵的倍數變化，快速篩選具有生物意義的差異代謝物",
      "parameter_knowledge":{ 
          "paired": {
            "type": "boolean",
            "options": [
                {
                  "value": "FALSE",
                  "label": "非配對樣本",
                  "description": "一般獨立組別設計。"
                },
                {
                  "value": "TRUE",
                  "label": "配對樣本",
                  "description": "同一受試者的前後測或配對設計。"
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """
        # Fold Change 分析
        mSet <- FC.Anal(
            mSet,
            fc.thresh = 2.0,    # 倍數變化閾值：fold change > 2 視為顯著差異
            cmp.type  = 0,      # 0 = 組別 1 - 組別 2
            {paired}
        )
        mSet <- PlotFC(mSet, "fc_0_", "png", 300, width=NA)
        """
    },
    "t-test": {
      "analysis": "t-test",
      "meaning": "檢定兩組樣本間各特徵的均值差異是否達到統計顯著水準",
      "parameter_knowledge":{
          "paired": {
            "type": "boolean",
            "options": [
                {
                  "value": "FALSE",
                  "label": "非配對樣本",
                  "description": "一般獨立組別設計。"
                },
                {
                  "value": "TRUE",
                  "label": "配對樣本",
                  "description": "同一受試者的前後測或配對設計。"
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """

        # t-test 分析
        mSet <- Ttests.Anal(
            mSet,
            nonpar   = FALSE,    # FALSE = 使用參數型 t-test（資料已正規化接近常態）
                                 # TRUE  = 改用非參數檢定（樣本數極少時）
            threshp  = 0.05,     # adjusted p-value (FDR) cutoff
            paired   = {paired}, # 是否配對
            equal.var= TRUE,     # TRUE = 假設等變異數（Student's t-test）
                                 # FALSE = 不假設等變異數（Welch's t-test，通常更保守）
            "fdr",               # 校正後的顯著性標準
            FALSE                # FALSE = 只輸出顯著的代謝物
        )
        mSet <- PlotTT(mSet, "tt_0_", "png", 300, width=NA)
        """
    },
    "volcano": {
      "analysis": "volcano",
      "meaning": "同時呈現倍數變化與統計顯著性，直觀標示最重要的差異特徵",
      "parameter_knowledge":{
          "paired": {
            "type": "boolean",
            "options": [
                {
                  "value": "FALSE",
                  "label": "非配對樣本",
                  "description": "一般獨立組別設計。"
                },
                {
                  "value": "TRUE",
                  "label": "配對樣本",
                  "description": "同一受試者的前後測或配對設計。"
                }
              ],
            "default": "FALSE"
          },
        },
      "full_code": """
        # 火山圖分析
        mSet <- Volcano.Anal(
            mSet, 
            {paired},  # 是否配對
            2.0,       # 倍數變化閾值：fold change > 2 視為顯著差異
            0,         # 0 = 組別 1 vs 組別 2
            F,         # FALSE = 使用參數型 t-test（資料已正規化接近常態）
            0.05,      # p-value threshold
            TRUE,      # TRUE = 假設等變異數（Student's t-test）
            "fdr"      # raw p-values，也可以用"fdr"
        )
        mSet <- PlotVolcano(mSet, "volcano_0_", 1, 0, format ="png", dpi=300, width=NA)
        """
    },
    "anova": {
      "analysis": "anova",
      "meaning": "檢定三組或以上樣本間是否存在顯著差異",
      "parameter_knowledge":{ 
        },
      "full_code": """
        # ANOVA
        mSet <- ANOVA.Anal(
          mSet, 
          F,      # FALSE = 使用參數型 t-test（資料已正規化接近常態）
          0.05,   # p-value threshold
          FALSE   # FALSE = 只輸出顯著的代謝物
        )
        mSet <- PlotANOVA(mSet, "aov_0_", "png", 300, width=NA)
        """
    },
    "pls-da": {
      "analysis": "pls-da",
      "meaning": "一種監督式分析，用於最大化組間差異並尋找特徵標誌 (Biomarkers)",
      "parameter_knowledge":{ 
        },
      "full_code": """
        # PLS-DA 圖表輸出
        mSet <- PLSR.Anal(mSet) 

        # Score Plot：觀察 PLS-DA 分類效果
        mSet <- PlotPLSPairSummary(mSet, "pls_pair_0_", "png", 300, width=NA, 5)
        mSet <- PlotPLS2DScore(
            mSet,
            "pls_score2d_0_",
            format     = "png",
            dpi        = 300,
            width      = NA,
            1,    # 第 1 潛在變數
            2,    # 第 2 潛在變數
            0.95,
            1,
            0
        )
        mSet<-PlotPLS3DScoreImg(mSet, "pls_score3d_0_", "png", 300, width=NA, 1,2,3, 40)
        mSet<-PlotPLSLoading(mSet, "pls_loading_0_", "png", 300, width=NA, 1, 2)

        # 交叉驗證（Cross-Validation, CV）
        mSet<-PLSDA.CV(mSet)
        mSet<-PlotPLS.Classification(mSet, "pls_cv_0_", "png", 300, width=NA)
        mSet<-PlotPLS.Imp(mSet, "pls_imp_0_", "png", 300, width=NA, "vip", "Comp. 1", 15, FALSE) # "vip": VIp scores,"type": coefficients

        # 置換檢驗 (Permutation Test)
        mSet <- PLSDA.Permut(mSet, 100, "accu")
        mSet <- PlotPLS.Permutation(mSet, "pls_perm_0_", "png", 300, width=NA)
        """
    },
    "correlation_heatmap": {
      "analysis": "correlation_heatmap",
      "meaning": "繪製相關性分析",
      "parameter_knowledge":{ 
          "paired": {
            "type": "string",
            "options": [
                {
                  "value": "row",
                  "label": "features",
                  "description": "針對代謝物繪製相關性分析"
                },
                {
                  "value": "col",
                  "label": "samples",
                  "description": "針對樣本繪製相關性分析"
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
          "col",       # 選擇要計算相關的對象 "row": features, "col": samples
          "pearson",   # 計算方法 'pearson', 'spearman', or 'kendall'
          "bwm",       # 顏色 "bwm": default, "gbr": red/green, "heat": heat colors, "topo": topo colors, "gray": gray scale.
          TRUE,        # fix colors
          TRUE,        # clustered
          0.3,         # 相關係數的截斷值
          "overview"   # "overview" or "detail" of the heatmap
        )
        """
    },
    "clustering": {
      "analysis": "clustering",
      "meaning": "聚類分析",
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
          "ward.D"     # clustering algorithm: average, complete, single 試試看
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
      "meaning": "隨機森林",
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
      "meaning": "隨機森林",
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