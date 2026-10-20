from pathlib import Path
from devsnap.transport.git_plumbing import (
    _run_git,
    create_git_commit,
    create_git_tree,
    extract_git_blob,
    save_state_to_git,
    update_git_ref,
    write_git_blob,
)


def test_git_plumbing_storage(tmp_path: Path):
    # Initialize bare or normal repo in tmp_path
    rc, out, err = _run_git(["init"], cwd=tmp_path)
    assert rc == 0

    # Create dummy archive
    test_archive = tmp_path / "test_state.tar.gz.age"
    test_content = b"DevSnap Encrypted State Blob V1 Payload Content"
    test_archive.write_bytes(test_content)

    # 1. Store blob
    blob_sha = write_git_blob(test_archive, cwd=tmp_path)
    assert len(blob_sha) == 40

    # 2. Store tree
    tree_sha = create_git_tree(blob_sha, filename="state.tar.gz.age", cwd=tmp_path)
    assert len(tree_sha) == 40

    # 3. Create commit
    commit_sha = create_git_commit(tree_sha, message="devsnap test save", cwd=tmp_path)
    assert len(commit_sha) == 40

    # 4. Update ref
    ref_name = "refs/devsnap/latest"
    update_git_ref(ref_name, commit_sha, cwd=tmp_path)

    # 5. Extract blob using cat-file
    restored_file = tmp_path / "restored.tar.gz.age"
    ok = extract_git_blob(restored_file, ref_name=ref_name, filename="state.tar.gz.age", cwd=tmp_path)
    assert ok is True
    assert restored_file.read_bytes() == test_content


def test_save_state_to_git_helper(tmp_path: Path):
    _run_git(["init"], cwd=tmp_path)

    archive = tmp_path / "snap.tar.gz.age"
    archive.write_bytes(b"HELLO_WORLD_SNAPSHOT")

    commit_sha = save_state_to_git(archive, message="automated snapshot", cwd=tmp_path)
    assert len(commit_sha) == 40

    out_file = tmp_path / "recovered.tar.gz.age"
    assert extract_git_blob(out_file, ref_name="refs/devsnap/latest", cwd=tmp_path) is True
    assert out_file.read_bytes() == b"HELLO_WORLD_SNAPSHOT"
