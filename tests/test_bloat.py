import pytest
import json
from app.core.bloat import BloatAnalyzer
from app.models import ImageArtifact

def test_bloat_analyzer_heuristics():
    """Test bloat detection logic"""
    
    # Case 1: Small optimized image
    res = BloatAnalyzer.analyze_image(["nginx:alpine"], 20 * 1024**2) # 20MB
    assert res['score'] == 100
    assert len(res['issues']) == 0
    
    # Case 2: Large unoptimized image
    res = BloatAnalyzer.analyze_image(["python:3.9"], 950 * 1024**2) # 950MB
    assert res['score'] < 100
    assert any("Large image size" in i for i in res['issues'])
    assert any("unoptimized" in i for i in res['issues'])
    
    # Case 3: Huge image (Critical)
    res = BloatAnalyzer.analyze_image(["my-app:latest"], 1.5 * 1024**3) # 1.5GB
    assert res['score'] <= 60
    assert any("Huge image size" in i for i in res['issues'])

def test_bloat_integration_mock():
    """Test integration logic manually since E2E requires docker"""
    # Simulate what happens in the route
    img = ImageArtifact(
        tags=["python:3.9"],
        size_bytes=900 * 1024**2,
        bloat_issues='["Issue 1", "Issue 2"]',
        bloat_score=60
    )
    
    # Access property directly
    assert img.issues_list == ["Issue 1", "Issue 2"]
    
    # Test empty issues
    img2 = ImageArtifact(bloat_issues=None)
    assert img2.issues_list == []
    
    # Test invalid json
    img3 = ImageArtifact(bloat_issues="Raw String")
    assert img3.issues_list == ["Raw String"]
