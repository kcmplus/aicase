// Payment return URLs describe navigation, never proof of payment.
export function paymentState(order,{returned=false,exhausted=false}={}){
 if(order.refund){
  const status=order.refund.status;
  const titles={requested:'Checking refund status.',pending:'Refund processing.',succeeded:'Payment refunded.',failed:'Refund could not be completed.'};
  const messages={requested:'Your refund request is saved. Contact support to confirm its status.',pending:'Your refund is being processed. Please do not pay again.',succeeded:'Your payment provider has confirmed the refund. Your bank determines when it reaches your account.',failed:'The payment provider could not complete your refund. Please contact support.'};
  return {pending:false,fulfilled:false,canPay:false,showCode:false,showNewOrder:status==='succeeded',title:titles[status]||titles.requested,message:messages[status]||messages.requested};
 }
 const fulfilled=['paid','printing','ready','completed','collected'].includes(order.status);
 const pending=order.status==='pending',closed=order.status==='cancelled';
 const delivery=['courier','air'].includes(order.fulfillmentType);
 const free=order.mode==='free_test';
 const titles={paid:'Payment received.',printing:'Your case is printing.',ready:'Your case is ready.',completed:'Your order is complete.',collected:'Your order is complete.'};
 const messages={paid:'Your payment is confirmed and your design is saved.',printing:'Payment is confirmed. Your order is being printed.',ready:'Your order is ready. Follow the collection instructions at the station.',completed:'Your order is complete. Thank you for creating with us.',collected:'Your order is complete. Thank you for creating with us.'};
 return {pending,fulfilled,canPay:pending&&!returned,showCode:fulfilled,
  title:free&&order.status==='paid'?'No-charge order confirmed.':delivery&&fulfilled?'Your delivery order.':titles[order.status]||(pending?(returned?'Confirming your payment…':'Your case is waiting.'):closed?'Checkout closed.':'Checking order status.'),
  message:free&&order.status==='paid'?'No payment is required. Confirm the station to send this test order.':delivery&&fulfilled?'Your payment is confirmed. Contact support for delivery updates.':messages[order.status]||(pending?(exhausted?'Confirmation is taking longer than usual. If you have already paid, do not pay again. Refresh the status later or keep your order number for support.':returned?'We are waiting for payment confirmation. Please do not pay again; this page will update automatically.':'Your order is saved and awaiting payment. If you have already paid, refresh the status before trying again.'):closed?'This checkout is closed. Check your payment record before creating another order.':'Refresh to get the latest order status.'),
  showNewOrder:fulfilled||closed};
}
