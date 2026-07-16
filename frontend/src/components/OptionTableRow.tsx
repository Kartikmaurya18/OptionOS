import { memo, type CSSProperties } from "react";

import { FlashValue } from "@/components/FlashValue";
import { TableCell, TableRow } from "@/components/ui/table";
import { useOptionRow } from "@/hooks/useOptionRow";
import { formatPrice, formatStrike } from "@/utils/format";

interface OptionTableRowProps {
  strike: number;
  style: CSSProperties;
}

function OptionTableRowImpl({ strike, style }: OptionTableRowProps) {
  // Subscribes to only this strike -- a tick for another row never
  // re-renders this component.
  const row = useOptionRow(strike);

  return (
    <TableRow style={style} className="absolute left-0 top-0 w-full">
      <TableCell className="font-medium text-call">
        <FlashValue value={row?.callLtp} format={formatPrice} />
      </TableCell>
      <TableCell className="font-medium text-put">
        <FlashValue value={row?.putLtp} format={formatPrice} />
      </TableCell>
      <TableCell className="font-semibold text-strike">{formatStrike(strike)}</TableCell>
      <TableCell className="font-semibold text-straddle">
        <FlashValue value={row?.straddle} format={formatPrice} />
      </TableCell>
    </TableRow>
  );
}

export const OptionTableRow = memo(OptionTableRowImpl);
