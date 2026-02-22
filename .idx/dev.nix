let
  nixpkgs = fetchTarball "https://github.com/NixOS/nixpkgs/archive/refs/tags/24.05.tar.gz";
  pkgs = import nixpkgs { config = {}; overlays = []; };
in
{ pkgs, ... }: {
  channel = "stable-24.05";

  packages = [
    # Base packages
    pkgs.git
    (pkgs.python311.withPackages (ps: with ps; [
      # Python libraries from nixpkgs
      requests
      konlpy
      python-levenshtein
      
      # PyKoSpacing from git using fetchPypi
      (buildPythonPackage rec {
        pname = "pykospacing";
        version = "0.5";
        src = pkgs.fetchPypi {
          inherit pname version;
          sha256 = "0d2b2748b69c6f52b75be72b95a8e3d6e5347f71758e57866a9c1488b857778b";
        };
        doCheck = false;
        propagatedBuildInputs = [ six ];
      })
    ]))
  ];

  idx = {
    extensions = [];
    previews = {
      enable = true;
    };
    workspace = {
      # No lifecycle hooks needed, Nix manages the environment
      onCreate = {};
      onStart = {};
    };
  };
}
