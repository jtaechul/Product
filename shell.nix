{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    python3Packages.pip # 'python3-pip' -> 'python3Packages.pip'으로 수정
  ];
}