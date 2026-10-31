// Payment return URLs describe navigation, never proof of payment.
export function paymentState(order,{returned=false,exhausted=false}={}){
 const fulfilled=['paid','printing','ready','completed','collected'].includes(order.status);
 const pending=order.status==='pending',closed=order.status==='cancelled';
 const titles={paid:'Payment received.',printing:'Your case is printing.',ready:'Your case is ready.',completed:'Your order is complete.',collected:'Your order is complete.'};
 const messages={paid:'Your payment is confirmed and your design is saved.',printing:'Payment is confirmed. Your order is being printed.',ready:'Your order is ready. Follow the collection instructions at the station.',completed:'Your order is complete. Thank you for creating with us.',collected:'Your order is complete. Thank you for creating with us.'};
 return {pending,fulfilled,canPay:pending&&!returned,showCode:fulfilled,
  title:titles[order.status]||(pending?(returned?'Confirming your payment…':'Your case is waiting.'):closed?'Checkout closed.':'Checking order status.'),
  message:messages[order.status]||(pending?(exhausted?'Confirmation is taking longer than usual. If you have already paid, do not pay again. Refresh the status later or keep your order number for support.':returned?'We are waiting for payment confirmation. Please do not pay again; this page will update automatically.':'Your order is saved and awaiting payment. If you have already paid, refresh the status before trying again.'):closed?'This checkout is closed. Check your payment record before creating another order.':'Refresh to get the latest order status.'),
  showNewOrder:fulfilled||closed};
}
