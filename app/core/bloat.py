"""GreenOps bloat analysis engine"""

class BloatAnalyzer:
    """Analyze images for potential optimization"""
    
    # Heuristics
    WARNING_SIZE_MB = 500
    CRITICAL_SIZE_MB = 1000
    
    OPTIMIZED_TAGS = ["slim", "alpine", "distroless", "light", "nano"]
    
    @classmethod
    def analyze_image(cls, image_tags: list[str], size_bytes: int) -> dict:
        """
        Analyze an image for bloat.
        Returns: { "score": int (0-100, 100=good), "issues": list[str] }
        """
        issues = []
        score = 100
        size_mb = size_bytes / (1024**2)
        
        # 1. Size Check
        if size_mb > cls.CRITICAL_SIZE_MB:
            issues.append(f"Huge image size ({size_mb:.0f}MB). Consider multi-stage builds.")
            score -= 40
        elif size_mb > cls.WARNING_SIZE_MB:
            issues.append(f"Large image size ({size_mb:.0f}MB).")
            score -= 20
            
        # 2. Tag Heuristics (only if we have tags)
        if image_tags:
            is_optimized = False
            for tag in image_tags:
                for opt in cls.OPTIMIZED_TAGS:
                    if opt in tag.lower():
                        is_optimized = True
                        break
            
            if not is_optimized and size_mb > 200:
                issues.append("Base image appears unoptimized (no 'slim' or 'alpine' tag).")
                score -= 20
                
        return {
            "score": max(0, score),
            "issues": issues
        }
