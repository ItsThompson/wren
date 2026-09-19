#!/usr/bin/env bash

validate_managed_markers() {
  local hosts_file=$1
  local marker_start=$2
  local marker_end=$3
  local state=outside
  local starts=0
  local ends=0
  local line

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "$marker_start" ]]; then
      if [[ "$state" != outside || "$starts" -ne 0 ]]; then
        printf 'hosts: duplicate or nested managed start marker in %s\n' "$hosts_file" >&2
        return 1
      fi
      state=inside
      starts=$((starts + 1))
      continue
    fi
    if [[ "$line" == "$marker_end" ]]; then
      if [[ "$state" != inside || "$ends" -ne 0 ]]; then
        printf 'hosts: misplaced or duplicate managed end marker in %s\n' "$hosts_file" >&2
        return 1
      fi
      state=outside
      ends=$((ends + 1))
    fi
  done < "$hosts_file"

  if [[ "$state" != outside || "$starts" -ne 1 || "$ends" -ne 1 ]]; then
    printf 'hosts: expected one complete managed marker block in %s\n' "$hosts_file" >&2
    return 1
  fi
}

get_host_file_mode() {
  local hosts_file=$1
  case "$(uname -s)" in
    Darwin) stat -f '%Lp' "$hosts_file" ;;
    Linux) stat -c '%a' "$hosts_file" ;;
    *)
      printf 'hosts: unsupported operating system for portable mode preservation\n' >&2
      return 1
      ;;
  esac
}
