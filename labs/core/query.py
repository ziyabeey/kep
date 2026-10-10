#!/usr/bin/env python3
"""Structured-query demo. NOT a natural-language model or a web consumer app."""
import argparse,json
from pathlib import Path
from kepcore.core import load_catalog,load_json,Query,decide
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--query',required=True,type=Path);a=p.parse_args()
    try:
        result=decide(load_catalog(),Query(**load_json(a.query)))
        print(json.dumps(result.to_dict(),ensure_ascii=False,indent=2))
    except (ValueError,TypeError,OSError,json.JSONDecodeError) as e:p.error(str(e))
