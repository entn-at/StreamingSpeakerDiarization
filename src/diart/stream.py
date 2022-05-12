from pathlib import Path
from typing import Union, Text

import rx.operators as ops

import diart.operators as dops
import diart.sources as src
from diart.pipelines import OnlineSpeakerDiarization
from diart.sinks import RealTimePlot, RTTMWriter


class RealTimeInference:
    def __init__(self, output_path: Union[Text, Path], do_plot: bool = True):
        self.output_path = Path(output_path).expanduser()
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.do_plot = do_plot

    def __call__(self, pipeline: OnlineSpeakerDiarization, source: src.AudioSource):
        rttm_writer = RTTMWriter(path=self.output_path / f"{source.uri}.rttm")
        observable = pipeline.from_source(source).pipe(
            dops.progress(f"Streaming {source.uri}", total=source.length, leave=True)
        )
        if not self.do_plot:
            # Write RTTM file only
            observable.subscribe(rttm_writer)
        else:
            # Write RTTM file + buffering and real-time plot
            observable.pipe(
                ops.do(rttm_writer),
                dops.buffer_output(
                    duration=pipeline.duration,
                    step=pipeline.config.step,
                    latency=pipeline.config.latency,
                    sample_rate=pipeline.sample_rate
                ),
            ).subscribe(RealTimePlot(pipeline.duration, pipeline.config.latency))
        # Stream audio through the pipeline
        source.read()


if __name__ == "__main__":
    import argparse
    import torch
    import diart.argdoc as argdoc
    from diart.pipelines import PipelineConfig

    # Define script arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=str, help="Path to an audio file | 'microphone'")
    parser.add_argument("--step", default=0.5, type=float, help=f"{argdoc.STEP}. Defaults to 0.5")
    parser.add_argument("--latency", default=0.5, type=float, help=f"{argdoc.LATENCY}. Defaults to 0.5")
    parser.add_argument("--tau", default=0.5, type=float, help=f"{argdoc.TAU}. Defaults to 0.5")
    parser.add_argument("--rho", default=0.3, type=float, help=f"{argdoc.RHO}. Defaults to 0.3")
    parser.add_argument("--delta", default=1, type=float, help=f"{argdoc.DELTA}. Defaults to 1")
    parser.add_argument("--gamma", default=3, type=float, help=f"{argdoc.GAMMA}. Defaults to 3")
    parser.add_argument("--beta", default=10, type=float, help=f"{argdoc.BETA}. Defaults to 10")
    parser.add_argument("--max-speakers", default=20, type=int, help=f"{argdoc.MAX_SPEAKERS}. Defaults to 20")
    parser.add_argument("--no-plot", dest="no_plot", action="store_true", help="Skip plotting for faster inference")
    parser.add_argument("--gpu", dest="gpu", action="store_true", help=argdoc.GPU)
    parser.add_argument("--output", type=str, help=f"{argdoc.OUTPUT}. Defaults to home directory if SOURCE == 'microphone' or parent directory if SOURCE is a file")
    args = parser.parse_args()

    # Define online speaker diarization pipeline
    pipeline = OnlineSpeakerDiarization(PipelineConfig(
        step=args.step,
        latency=args.latency,
        tau_active=args.tau,
        rho_update=args.rho,
        delta_new=args.delta,
        gamma=args.gamma,
        beta=args.beta,
        max_speakers=args.max_speakers,
        device=torch.device("cuda") if args.gpu else None,
    ))

    # Manage audio source
    if args.source != "microphone":
        args.source = Path(args.source).expanduser()
        args.output = args.source.parent if args.output is None else Path(args.output)
        audio_source = src.FileAudioSource(
            file=args.source,
            uri=args.source.stem,
            reader=src.RegularAudioFileReader(
                pipeline.sample_rate, pipeline.duration, pipeline.config.step
            ),
        )
    else:
        args.output = Path("~/").expanduser() if args.output is None else Path(args.output)
        audio_source = src.MicrophoneAudioSource(pipeline.sample_rate)

    # Run online inference
    RealTimeInference(args.output, do_plot=not args.no_plot)(pipeline, audio_source)