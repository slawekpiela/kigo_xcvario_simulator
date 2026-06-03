Sample IGC flight logs for the simulated XCVario/IGC FLARM logger.

These files were copied from the local `kigo_nav/test/data` fixtures because
`kigo_nav/logs` currently contains no recorded `.igc` files. At runtime the
simulator first checks the sibling `../kigo_nav/logs` directory and uses those
real logs when present; otherwise it falls back to these packaged samples.
