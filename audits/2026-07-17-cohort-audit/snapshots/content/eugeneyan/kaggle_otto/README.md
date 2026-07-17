# Otto
Code for 85th place (out of 3514) in Kaggle Otto Production Classification Challenge (private leaderboard).
* Link: https://www.kaggle.com/c/otto-group-product-classification-challenge 

# Feature engineering (not all are used in final ensemble)
* Sum of all features for each row
* Variance of all features for each row
* Number of filled features for each row
* Operational features (+, -, *, /) created on top 20 features (does not work all the time)
* Transforming features with mean-standarization (new feature = original feature - column mean)

# Models
* XGBoost
* Neural Networks (using Lasagna and H20; only Lasagna model was used for final ensemble)
* randomForest

# Software
* R 3.1.3
* R packages:
  - doParallel
  - Caret
  - xgboost
  - party
  - glmnet
  - dplyr

* Python 2.7
* Python libraries:
  - Lasagna
  - numpy
  - scipy
  - theano
