# NeuroVEP Project Context

**Domain**: Neuroscience / Neurophysiology / Signal Processing
**Repositories**: 5 (neurovep-data, neurovep-core, neurovep-nnlib, neurovep-present-android, super-utils)

## VEP Domain Knowledge

**VEP (Visual Evoked Potential)**: Electrical signal from visual cortex in response to checkerboard pattern reversal.

**Key Components**:
- **P100**: Positive peak ~100ms (primary diagnostic marker)
- **N75**: Negative peak ~75ms (early visual processing)
- **N145**: Negative peak ~145ms (later processing stage)

**Clinical Significance**: Latency/amplitude changes indicate optic nerve pathology, demyelination, visual pathway lesions.

## Analysis Workflows

1. **Load Raw Data**: EEG from /dropbox_Neurofieldz2
2. **Preprocess**: 0.5-100 Hz filtering, artifact rejection
3. **Extract Components**: P100, N75, N145 peak detection
4. **Statistical Analysis**: Latency, amplitude, variability metrics
5. **Visualization**: Waveforms, topographic maps
6. **Report Generation**: Clinical summaries

## Repository Structure

- **neurovep-data**: Data loading, preprocessing utilities
- **neurovep-core**: Core VEP analysis algorithms
- **neurovep-nnlib**: Neural network models for VEP
- **neurovep-present-android**: Presentation software
- **super-utils**: Shared utility functions

## Dependencies

Installed in neurovep_data conda environment:
- PyTorch 2.7.1 (CPU-only)
- scipy, statsmodels, scikit-learn
- seaborn, matplotlib (Agg backend)
- asdf, filterpy, pywavelets, imageio

## Collaboration Guidelines

- **Code Style**: Follow neurovep-core conventions
- **Testing**: Validate with TestEng before committing
- **Documentation**: Document analysis methods clearly
- **Reproducibility**: Use fixed random seeds, version data
