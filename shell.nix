
{ pkgs ? import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/refs/tags/24.05.tar.gz") {} }:

let
  pykospacing = pkgs.python311Packages.buildPythonPackage rec {
    pname = "pykospacing";
    version = "0.5"; # Version from setup.py

    src = pkgs.fetchgit {
      url = "https://github.com/haven-jeon/PyKoSpacing.git";
      # Last commit hash on the main branch
      rev = "e3305457782637254e4c9c452485599e03d15442";
    };

    propagatedBuildInputs = with pkgs.python311Packages; [ tensorflow ];
  };

in
pkgs.mkShell {
  buildInputs = [
    pkgs.git
    pkgs.oraclejdk # Konlpy needs a JDK

    (pkgs.python311.withPackages (ps: [
      ps.requests
      ps.konlpy
      ps.python-levenshtein
      pykospacing
    ]))
  ];
}
