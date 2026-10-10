#!/usr/bin/env python3
"""Inspect withheld historical ratings. This is not a live restaurant recommendation."""
from __future__ import annotations
import argparse,json,sys
from benchmarks.ratings import load_ratings,split_rows
from kepcore.preferences import PreferenceModel

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user',default='U1001')
    p.add_argument('--method',choices=['global_mean','item_mean','user_mean','bias','item_knn'],default='user_mean')
    p.add_argument('--regularization',type=float,default=5)
    args=p.parse_args()
    rows,_=load_ratings();train,valid,test,_=split_rows(rows,20261010)
    model=PreferenceModel(args.method,args.regularization,15).fit(train+valid)
    held=[r for r in test if r.user==args.user]
    if not held:
        print('Bu kullanıcı için sabit test bölümünde kayıt yok. Örnek kullanıcı: U1001',file=sys.stderr);return 2
    result={'user':args.user,'method':args.method,'historical_only':True,'model_api_called':False,
            'note':'Gerçek puanlar yalnız değerlendirme için gösterilir; model fit verisine dahil edilmez.',
            'predictions':[{'restaurant_id':r.item,'predicted_rating':round(model.predict(r.user,r.item),4),'withheld_actual_rating':r.value,'training_support':model.support(r.user,r.item)} for r in held]}
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':sys.exit(main())
