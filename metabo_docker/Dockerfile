FROM hidakakombu/metaboanalystr_4.0.0:1.2

RUN apt-get update && apt-get install -y curl

RUN R -e "install.packages('ellipse', repos='https://cran.rstudio.com/')"
RUN R -e "install.packages('vegan', repos = c('https://vegandevs.r-universe.dev','https://cloud.r-project.org'))"
RUN R -e "install.packages('pls')"
RUN R -e "install.packages('iheatmapr')"
RUN R -e "install.packages('ggrepel')"
RUN R -e "install.packages('factoextra')"