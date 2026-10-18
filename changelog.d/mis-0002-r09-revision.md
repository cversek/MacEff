### Changed

- **MIS-0002-R09, revised in place** (`framework/mis/MIS-0002-persistent-layer.md`). A declared unit states its exit-code contract only when the default isn't the one it means: exit 0 is success, and exit 78 asks not to be restarted. The declaration model and the `persistent_layer` policy already work this way, so no declaration changes. This is the first revision under MIS-0001's new procedure. It takes no MIS number, a note under R09 links its previous text, and the slug is unchanged, so every citation still holds. R09's row names the test that decides it, which passes.
