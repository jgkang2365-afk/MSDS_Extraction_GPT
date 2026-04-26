# Task: MSDS GUI System Reconstruction (Track 2 Unification)

- [x] **Phase 1: Bloatware Removal**
    - [x] Remove `sqlite3`, `thefuzz` from imports
    - [x] Delete `KnowledgeManager` and related DB logic
    - [x] Delete `MatchingWorker` and matching UI code
    - [x] Remove `GraphifyIndexerThread` and background indexing
- [x] **Phase 2: Save Logic Refactoring**
    - [x] Rewrite `perform_standard_save` to use GUI table data directly
    - [x] Implement sequential saving based on `self.results` order
    - [x] Remove legacy matching maps (`usage_map`, `index_map`)
- [x] **Phase 3: Final Polishing**
    - [x] Restore `switch_page` for sidebar navigation
    - [x] Update help dialog text
    - [x] Final code audit for potential crashes
- [x] **Verification (FTF Protocol)**
    - [x] Forest: Architecture audit (Completed)
    - [x] Tree: Precision edits (Completed)
    - [x] Forest: Post-verification (Completed)
