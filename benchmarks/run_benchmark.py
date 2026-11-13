"""Entry point: python -m benchmarks.run_benchmark --models ..."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from .runner import run
from .report import create_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',nargs='+',default=['qwen3.5:4b','qwen3.5:9b'])
    parser.add_argument('--dataset',type=Path,default=Path(__file__).parent/'cases'/'dataset.json')
    parser.add_argument('--output',type=Path,default=Path.home()/'.forgeapply'/'benchmarks'/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--trials',type=int,default=3)
    parser.add_argument('--context',type=int,default=8192)
    parser.add_argument('--num-predict',type=int,default=768)
    parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--base-url',default='http://127.0.0.1:11434')
    parser.add_argument('--think',action='store_true')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--report-only',action='store_true')
    parser.add_argument('--categories',nargs='+')
    args=parser.parse_args()
    if args.trials<1 or args.context<1024 or args.num_predict<32: parser.error('Invalid trial/context/token limits')
    if not args.report_only:
        run(models=args.models,dataset=args.dataset,output=args.output,trials=args.trials,context=args.context,
            num_predict=args.num_predict,timeout=args.timeout,base_url=args.base_url,think=args.think,
            resume=args.resume,only_categories=args.categories)
    summary=create_report(args.output)
    print('Report:',args.output/'REPORT.md',flush=True)
    print('Recommendation:',summary['recommendation'],flush=True)


if __name__=='__main__': main()
